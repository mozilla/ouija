from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base


engine = create_engine('mysql+mysqldb://root:root@localhost/ouija2', echo=True)
Session = sessionmaker(engine)

session = Session()
