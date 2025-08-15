import uuid
from datetime import datetime
from app import db
from sqlalchemy.dialects.postgresql import UUID

class Project(db.Model):
    """
    A table for managing projects.
    """
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    description = db.Column(db.String(500), nullable=False)
    created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed = db.Column(db.Boolean, default=False)
    transactions = db.relationship('Transaction', backref='project', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Project id={self.id}, description={self.description}>'

class Transaction(db.Model):
    """
    A table for managing transactions related to a project.
    """
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transdate = db.Column(db.DateTime, nullable=False)
    desc = db.Column(db.String(250), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    category = db.Column(db.String(150), nullable=True)
    sourceAcc = db.Column(db.String(150), db.ForeignKey('asset.name'), nullable=True)
    destinationAcc = db.Column(db.String(150), nullable=True)
    score = db.Column(db.Numeric(10, 2), nullable=True)
    project_id = db.Column(UUID(as_uuid=True), db.ForeignKey('project.id'), nullable=False)

    source_asset = db.relationship('Asset', backref='transactions')

    def __repr__(self):
        return f'<Transaction id={self.id}, desc={self.desc}>'

class Category(db.Model):
    """
    A table for managing distinct categories for transactions.
    """
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(150), nullable=False)
    destinationAcc = db.Column(db.String(150), nullable=False)

    def __repr__(self):
        return f'<Category id={self.id}, key={self.key}>'

class Asset(db.Model):
    """
    A table for managing assets for the source account.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)

    def __repr__(self):
        return f'<Asset id={self.id}, name={self.name}>'
    
class UserCorrection(db.Model):
    """
    A table to store user-made corrections to transaction categories and destination accounts.
    This data is used to improve the scoring logic for future imports.
    """
    id = db.Column(db.Integer, primary_key=True)
    desc = db.Column(db.String(250), nullable=False)
    category = db.Column(db.String(150), nullable=False)
    destinationAcc = db.Column(db.String(150), nullable=False)

    def __repr__(self):
        return f'<UserCorrection id={self.id}, desc={self.desc}>'