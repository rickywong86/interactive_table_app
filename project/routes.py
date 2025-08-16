from flask import render_template, Blueprint, request, redirect, url_for, flash, jsonify, Response
from app import db
from .models import Project, Transaction, Category, Asset, UserCorrection
from datetime import datetime
import random
import csv
import io
from sentence_transformers import SentenceTransformer, util

project = Blueprint('project', __name__)

@project.route('/')
def index():
    """Renders the main project table page with pagination and search functionality."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search_query = request.args.get('search', '', type=str)

    query = Project.query
    if search_query:
        query = query.filter(Project.description.like(f'%{search_query}%'))

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    assets = Asset.query.order_by(Asset.name).all()

    return render_template('index.html', pagination=pagination, search_query=search_query, per_page=per_page, assets=assets)

@project.route('/projects/<uuid:project_id>')
def project_details(project_id):
    """Render the project details page for a specific project ID."""
    project_instance = Project.query.get_or_404(project_id)
    highlight_id = request.args.get('highlight_id', type=int)
    return render_template('project_details.html', project=project_instance, highlight_id=highlight_id)

@project.route('/project/create', methods=['POST'])
def create_project():
    """Creates a new project from form data."""
    description = request.form['description']
    completed = 'completed' in request.form
    new_project = Project(description=description, completed=completed)
    db.session.add(new_project)
    db.session.commit()
    flash('Project created successfully!', 'success')
    return redirect(url_for('project.index', highlight_id=new_project.id))

@project.route('/project/<int:project_id>/update', methods=['POST'])
def update_project(project_id):
    """Updates an existing project."""
    project_to_update = Project.query.get_or_404(project_id)
    project_to_update.description = request.form['description']
    project_to_update.completed = 'completed' in request.form
    db.session.commit()
    flash('Project updated successfully!', 'success')
    return redirect(url_for('project.index', highlight_id=project_to_update.id))

@project.route('/project/<int:project_id>/delete', methods=['POST'])
def delete_project(project_id):
    """Deletes a project by its ID."""
    project_to_delete = Project.query.get_or_404(project_id)
    db.session.delete(project_to_delete)
    db.session.commit()
    flash('Project deleted successfully!', 'danger')
    return redirect(url_for('project.index'))

@project.route('/project/<uuid:project_id>/transactions', methods=['GET'])
def get_transactions(project_id):
    """API endpoint to get paginated transactions for a project."""
    project_instance = Project.query.get_or_404(project_id)
    
    # Get pagination parameters from the request
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    transactions_query = Transaction.query.filter_by(project_id=project_id).order_by(Transaction.transdate.desc())
    pagination = transactions_query.paginate(page=page, per_page=per_page, error_out=False)

    transactions_list = []
    for t in pagination.items:
        try:
            transactions_list.append({
                'id': t.id,
                'transdate': t.transdate.isoformat(),
                'desc': t.desc,
                'amount': t.amount,
                'category': t.category,
                'sourceAcc': t.sourceAcc,
                'destinationAcc': t.destinationAcc,
                'score': t.score
            })
        except Exception as e:
            # This is where the error is likely happening.
            # Print the transaction ID to help with debugging.
            print(f"Error serializing transaction ID {t.id}: {e}")
            # Skip the problematic transaction and continue.
            continue

    return jsonify({
        'id': project_instance.id,
        'description': project_instance.description,
        'created': project_instance.created.isoformat(),
        'completed': project_instance.completed,
        'transactions': transactions_list,
        'has_next': pagination.has_next,
        'has_prev': pagination.has_prev,
        'next_num': pagination.next_num,
        'prev_num': pagination.prev_num,
        'page': pagination.page,
        'pages': pagination.pages,
        'per_page': pagination.per_page
    })

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

@project.route('/project/<uuid:project_id>/refresh_scores', methods=['POST'])
def refresh_project_scores(project_id):
    """
    API endpoint to refresh semantic scores for all transactions in a project.
    """
    transactions = Transaction.query.filter_by(project_id=project_id).all()
    _rescore_transactions(transactions)
    return jsonify({'message': 'All transaction scores refreshed successfully!'})

@project.route('/transaction/<uuid:transaction_id>/refresh_score', methods=['POST'])
def refresh_transaction_score(transaction_id):
    """
    API endpoint to refresh the semantic score for a single transaction.
    """
    transaction = Transaction.query.get_or_404(transaction_id)
    _rescore_transactions([transaction])
    return jsonify({'message': 'Transaction score refreshed successfully!'})

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

@project.route('/project/<uuid:project_id>/upload', methods=['POST'])
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

@project.route('/project/<uuid:project_id>/export_csv', methods=['GET'])
def export_csv(project_id):
    """Exports all transactions for a project to a CSV file."""
    project_instance = Project.query.get_or_404(project_id)
    transactions = project_instance.transactions

    # Prepare CSV data
    si = io.StringIO()
    cw = csv.writer(si)
    
    # Headers in the specified order
    headers = ['source account', 'Description', 'destination account', 'Date', 'Amount', 'category']
    cw.writerow(headers)

    for t in transactions:
        row = [
            t.sourceAcc,
            t.desc,
            t.destinationAcc,
            t.transdate.strftime('%Y%m%d') if t.transdate else '',
            t.amount,
            t.category,
        ]
        cw.writerow(row)

    output = si.getvalue()
    si.close()

    # Generate filename from project description
    filename = f"{project_instance.description.replace(' ', '_').replace('/', '-')}_transactions.csv"
    
    response = Response(output, mimetype='text/csv')
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response

@project.route('/transaction/<uuid:transaction_id>/update', methods=['PUT'])
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
    # transaction_record.sourceAcc = data.get('sourceAcc', transaction_record.sourceAcc)
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

@project.route('/transaction/<uuid:transaction_id>/delete', methods=['DELETE'])
def delete_transaction(transaction_id):
    """
    API endpoint to delete a transaction.
    """
    transaction_record = Transaction.query.get_or_404(transaction_id)
    db.session.delete(transaction_record)
    db.session.commit()
    return jsonify({'message': 'Transaction deleted successfully!'})

@project.route('/project/<uuid:project_id>/transactions/delete_all', methods=['DELETE'])
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

@project.route('/categories/list', methods=['GET'])
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

@project.route('/assets/list', methods=['GET'])
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

@project.route('/asset/create', methods=['POST'])
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

@project.route('/asset/<int:asset_id>/delete', methods=['POST'])
def delete_asset(asset_id):
    """
    Handles the deletion of an asset.
    """
    asset_record = Asset.query.get_or_404(asset_id)
    db.session.delete(asset_record)
    db.session.commit()
    flash(f'Asset "{asset_record.name}" deleted successfully!', 'success')
    return redirect(url_for('project.index'))

@project.route('/categories/list')
def list_categories():
    """API endpoint to list all unique categories and destination accounts."""
    transactions = Transaction.query.all()
    
    unique_categories = sorted(list(set(t.category for t in transactions if t.category)))
    unique_dest_accs = sorted(list(set(t.destinationAcc for t in transactions if t.destinationAcc)))

    return jsonify([
        {'category': c, 'destinationAcc': d}
        for c, d in zip(unique_categories, unique_dest_accs)
    ])
