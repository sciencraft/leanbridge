import env_setup
from config import settings
from database import engine, Base, SessionLocal
import crud
from auth import strengthen

def init_db():
    print("Initializing database...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # Create default users
        default_users = {
            "user": "password",
            "xurongge": "password",
            "daihui": "password",
        }
        
        for username, password in default_users.items():
            if not crud.get_user_by_username(db, username):
                password_hash = strengthen(password, username)
                crud.create_user(db, username, password_hash)
                print(f"Created user: {username}")
                
                # Create default config for each user
                crud.create_user_config(
                    db, 
                    username, 
                    rag_api_key=settings.rag_api_key,
                    rag_base_url=settings.rag_base_url,
                    mcp_servers={
                        "code_agent": {},
                        "search_agent": {}
                    }
                )
        print("Database initialized successfully.")
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
