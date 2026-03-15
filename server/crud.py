import env_setup
from sqlalchemy.orm import Session
import database

def get_user_by_username(db: Session, username: str):
    return db.query(database.User).filter(database.User.username == username).first()

def get_user_config(db: Session, username: str):
    return db.query(database.UserConfig).filter(database.UserConfig.username == username).first()

def create_user(db: Session, username: str, password_hash: str):
    db_user = database.User(username=username, password_hash=password_hash)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def create_user_config(db: Session, username: str, rag_api_key: str = None, rag_base_url: str = None, mcp_servers: dict = None):
    if mcp_servers is None:
        mcp_servers = {}
    
    db_config = database.UserConfig(
        username=username,
        rag_api_key=rag_api_key,
        rag_base_url=rag_base_url,
        mcp_servers=mcp_servers
    )
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    return db_config
