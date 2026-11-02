from sqlalchemy import create_engine
engine = create_engine('sqlite:///')
print('Tables:', engine.table_names())