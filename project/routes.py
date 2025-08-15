from flask import Blueprint, render_template, request, url_for, redirect, flash, jsonify
from .models import Project, Transaction, Category, Asset, UserCorrection
from app import db
import uuid
from datetime import datetime
import csv
import io
from sentence_transformers import SentenceTransformer, util

project_bp = Blueprint('project', __name__)

@project_bp.route('/')
def index():
    """
    Main page route, displaying a paginated and searchable list of projects.
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search_query = request.args.get('search', '', type=str)
    highlight_id = request.args.get('highlight_id', None, type=str)

    query = Project.query
    if search_query:
        query = query.filter(Project.description.ilike(f'%{search_query}%'))

    pagination = query.paginate(page=page, per_page=per_page)
    return render_template('index.html', pagination=pagination, search_query=search_query, highlight_id=highlight_id, per_page=per_page)

@project_bp.route('/project/create', methods=['POST'])
def create_project():
    """
    Handles the creation of a new project.
    """
    description = request.form.get('description')
    completed = 'completed' in request.form
    new_project = Project(description=description, completed=completed)
    db.session.add(new_project)
    db.session.commit()
    flash('Project created successfully!', 'success')
    return redirect(url_for('project.index', highlight_id=new_project.id))

@project_bp.route('/project/<uuid:project_id>/update', methods=['POST'])
def update_project(project_id):
    """
    Handles the update of an existing project.
    """
    project_record = Project.query.get_or_404(project_id)
    project_record.description = request.form.get('description')
    project_record.completed = 'completed' in request.form
    db.session.commit()
    flash('Project updated successfully!', 'success')
    return redirect(url_for('project.index', highlight_id=project_record.id))

@project_bp.route('/project/<uuid:project_id>/delete', methods=['POST'])
def delete_project(project_id):
    """
    Handles the deletion of a project.
    """
    project_record = Project.query.get_or_404(project_id)
    db.session.delete(project_record)
    db.session.commit()
    flash('Project deleted successfully!', 'success')
    return redirect(url_for('project.index'))

def _rescore_transactions(transactions):
    """
    Helper function to re-score a list of transactions.
    """
    categories = Category.query.all()
    user_corrections = UserCorrection.query.all()

    labels = []
    labels.extend([c.key for c in categories])
    labels.extend([uc.desc for uc in user_corrections])

    sbert_model = SentenceTransformer('all-MiniLM-L6-v2')

    label_embeddings = sbert_model.encode(labels, convert_to_tensor=True)

    for transaction in transactions:
        desc_embedding = sbert_model.encode(transaction.desc, convert_to_tensor=True)
        cosine_scores = util.cos_sim(desc_embedding, label_embeddings)[0]
        best_match_index = cosine_scores.argmax()
        best_match_score = cosine_scores[best_match_index].item()
        
        if best_match_index < len(categories):
            matched_category = categories[best_match_index]
            transaction.category = matched_category.category
            transaction.destinationAcc = matched_category.destinationAcc
        else:
            matched_correction = user_corrections[best_match_index - len(categories)]
            transaction.category = matched_correction.category
            transaction.destinationAcc = matched_correction.destinationAcc
        
        transaction.score = best_match_score
    db.session.commit()

@project_bp.route('/project/<uuid:project_id>/refresh_scores', methods=['POST'])
def refresh_project_scores(project_id):
    """
    API endpoint to refresh semantic scores for all transactions in a project.
    """
    transactions = Transaction.query.filter_by(project_id=project_id).all()
    _rescore_transactions(transactions)
    return jsonify({'message': 'All transaction scores refreshed successfully!'})

@project_bp.route('/transaction/<uuid:transaction_id>/refresh_score', methods=['POST'])
def refresh_transaction_score(transaction_id):
    """
    API endpoint to refresh the semantic score for a single transaction.
    """
    transaction = Transaction.query.get_or_404(transaction_id)
    _rescore_transactions([transaction])
    return jsonify({'message': 'Transaction score refreshed successfully!'})

@project_bp.route('/project/<uuid:project_id>/transactions', methods=['GET'])
def get_project_transactions(project_id):
    """
    API endpoint to get a project's details and transactions in JSON format.
    """
    project_record = Project.query.get_or_404(project_id)
    transactions = Transaction.query.filter_by(project_id=project_id).order_by(Transaction.transdate).all()
    
    transactions_data = [{
        'id': transaction.id,
        'transdate': transaction.transdate.isoformat(),
        'desc': transaction.desc,
        'amount': str(transaction.amount),
        'category': transaction.category,
        'sourceAcc': transaction.sourceAcc,
        'destinationAcc': transaction.destinationAcc,
        'score': str(transaction.score) if transaction.score else None
    } for transaction in transactions]

    return jsonify({
        'id': project_record.id,
        'description': project_record.description,
        'created': project_record.created.isoformat(),
        'completed': project_record.completed,
        'transactions': transactions_data
    })

@project_bp.route('/project/<uuid:project_id>/upload', methods=['POST'])
def upload_transactions(project_id):
    """
    Handles the upload of a text file and imports transactions,
    with semantic scoring for category and destination account.
    """
    project_record = Project.query.get_or_404(project_id)
    
    if 'file' not in request.files:
        return jsonify({'message': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400

    source_asset_name = request.form.get('source_asset')
    
    # Load categories and user corrections for scoring
    categories = Category.query.all()
    user_corrections = UserCorrection.query.all()

    # Create a list of all potential labels to compare against
    labels = []
    labels.extend([c.key for c in categories])
    labels.extend([uc.desc for uc in user_corrections])

    
    sbert_model = SentenceTransformer('all-MiniLM-L6-v2')

    # Encode all labels for comparison
    label_embeddings = sbert_model.encode(labels, convert_to_tensor=True)
        
    if file:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.reader(stream)
        next(csv_reader) # Skip header row
        
        try:
            for row in csv_reader:
                # The CSV format is now: transdate,desc,amount,destinationAcc,score
                # The category and sourceAcc will be populated by the app
                transdate, desc, amount = row

                # Find the best matching category using semantic scoring
                desc_embedding = sbert_model.encode(desc, convert_to_tensor=True)
                
                # Compute cosine similarity between the description and all labels
                cosine_scores = util.cos_sim(desc_embedding, label_embeddings)[0]
                best_match_index = cosine_scores.argmax()
                best_match_score = cosine_scores[best_match_index].item()
                
                # Find the best matching category and destination account
                predicted_category = "Uncategorized"
                predicted_destinationAcc = ""
                
                if best_match_index < len(categories):
                    # Match found in Category table
                    matched_category = categories[best_match_index]
                    predicted_category = matched_category.category
                    predicted_destinationAcc = matched_category.destinationAcc
                else:
                    # Match found in UserCorrection table
                    matched_correction = user_corrections[best_match_index - len(categories)]
                    predicted_category = matched_correction.category
                    predicted_destinationAcc = matched_correction.destinationAcc

                new_transaction = Transaction(
                    project_id=project_id,
                    transdate=datetime.strptime(transdate, '%Y-%m-%d'),
                    desc=desc,
                    amount=amount,
                    category=predicted_category,
                    sourceAcc=source_asset_name,
                    destinationAcc=predicted_destinationAcc,
                    score=best_match_score  # Store the highest score for reference
                )
                db.session.add(new_transaction)
            db.session.commit()
            return jsonify({'message': 'Transactions imported successfully!'}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({'message': f'Error importing data: {e}'}), 500

@project_bp.route('/transaction/<uuid:transaction_id>/update', methods=['PUT'])
def update_transaction(transaction_id):
    """
    API endpoint to update an existing transaction and capture user corrections.
    """
    transaction_record = Transaction.query.get_or_404(transaction_id)
    data = request.json
    
    # Store the old values to check for changes
    old_category = transaction_record.category
    old_destinationAcc = transaction_record.destinationAcc

    # Update the transaction record
    transaction_record.category = data.get('category', old_category)
    transaction_record.sourceAcc = data.get('sourceAcc', transaction_record.sourceAcc)
    transaction_record.destinationAcc = data.get('destinationAcc', old_destinationAcc)
    
    # If the category or destination account was changed, save it as a UserCorrection
    if transaction_record.category != old_category or transaction_record.destinationAcc != old_destinationAcc:
        # Check if a correction already exists for this description
        correction = UserCorrection.query.filter_by(desc=transaction_record.desc).first()
        if correction:
            correction.category = transaction_record.category
            correction.destinationAcc = transaction_record.destinationAcc
        else:
            new_correction = UserCorrection(
                desc=transaction_record.desc,
                category=transaction_record.category,
                destinationAcc=transaction_record.destinationAcc
            )
            db.session.add(new_correction)
            
    db.session.commit()
    return jsonify({'message': 'Transaction updated successfully!'})

@project_bp.route('/transaction/<uuid:transaction_id>/delete', methods=['DELETE'])
def delete_transaction(transaction_id):
    """
    API endpoint to delete a transaction.
    """
    transaction_record = Transaction.query.get_or_404(transaction_id)
    db.session.delete(transaction_record)
    db.session.commit()
    return jsonify({'message': 'Transaction deleted successfully!'})

@project_bp.route('/project/<uuid:project_id>/transactions/delete_all', methods=['DELETE'])
def delete_all_transactions(project_id):
    """
    API endpoint to delete all transactions for a specific project.
    Can also delete transactions for a specific asset if `asset_name` is provided.
    """
    project_record = Project.query.get_or_404(project_id)
    asset_name = request.args.get('asset_name')

    if asset_name:
        transactions_to_delete = Transaction.query.filter_by(project_id=project_id, sourceAcc=asset_name).all()
        message = f'All transactions for project "{project_record.description}" from asset "{asset_name}" deleted successfully!'
    else:
        transactions_to_delete = Transaction.query.filter_by(project_id=project_id).all()
        message = f'All transactions for project "{project_record.description}" deleted successfully!'

    for transaction in transactions_to_delete:
        db.session.delete(transaction)
    
    db.session.commit()
    return jsonify({'message': message})

@project_bp.route('/categories/list', methods=['GET'])
def get_categories():
    """
    API endpoint to get a list of all categories.
    """
    categories = Category.query.all()
    categories_data = [{
        'key': c.key,
        'category': c.category,
        'destinationAcc': c.destinationAcc
    } for c in categories]
    return jsonify(categories_data)

@project_bp.route('/assets/list', methods=['GET'])
def get_assets():
    """
    API endpoint to get a list of all assets.
    """
    assets = Asset.query.all()
    assets_data = [{
        'id': a.id,
        'name': a.name,
    } for a in assets]
    return jsonify(assets_data)

@project_bp.route('/asset/create', methods=['POST'])
def create_asset():
    """
    Handles the creation of a new asset.
    """
    asset_name = request.form.get('name')
    if not asset_name:
        flash('Asset name is required.', 'danger')
        return redirect(url_for('project.index'))

    existing_asset = Asset.query.filter_by(name=asset_name).first()
    if existing_asset:
        flash('An asset with this name already exists.', 'warning')
        return redirect(url_for('project.index'))

    new_asset = Asset(name=asset_name)
    db.session.add(new_asset)
    db.session.commit()
    flash(f'Asset "{asset_name}" created successfully!', 'success')
    return redirect(url_for('project.index'))

@project_bp.route('/asset/<int:asset_id>/delete', methods=['POST'])
def delete_asset(asset_id):
    """
    Handles the deletion of an asset.
    """
    asset_record = Asset.query.get_or_404(asset_id)
    db.session.delete(asset_record)
    db.session.commit()
    flash(f'Asset "{asset_record.name}" deleted successfully!', 'success')
    return redirect(url_for('project.index'))

