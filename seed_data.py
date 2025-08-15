# seed_data.py
# Use this script to populate the database with sample data.

import os
import random
from app import create_app, db
from project.models import Asset, AssetColumnMapping

def seed_database():
    """
    Clears existing data and populates the database with 200 sample assets
    and their associated mappings.
    """
    app = create_app()
    with app.app_context():
        # Clear all existing data to ensure a clean slate.
        print("Clearing existing data...")
        db.session.query(AssetColumnMapping).delete()
        db.session.query(Asset).delete()
        db.session.commit()

        print("Seeding database with 200 sample assets...")
        for i in range(1, 201):
            asset = Asset(
                account_name=f"Sample Account {i}",
                has_header=random.choice([True, False])
            )
            db.session.add(asset)
            
            # Create a few mappings for each asset to demonstrate the relationship.
            num_mappings = random.randint(1, 5)
            for j in range(num_mappings):
                mapping = AssetColumnMapping(
                    asset=asset, # Link the mapping to the newly created asset
                    seq=j + 1,
                    src_column_name=f"source_col_{j+1}",
                    des_column_name=f"dest_col_{j+1}",
                    is_drop=random.choice([True, False]),
                    format=f"format_{j+1}",
                    custom=random.choice([True, False]),
                    custom_formula=f"formula_{j+1}"
                )
                db.session.add(mapping)
        
        db.session.commit()
        print("Database seeded successfully.")

if __name__ == '__main__':
    seed_database()
