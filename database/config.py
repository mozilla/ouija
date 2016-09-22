import os
import urlparse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# If we get exception here, we believe it's running on local environment.
# Otherwise, the configuration is for heroku and postgresql
try:
    DBURL = urlparse.urlparse(os.environ["DATABASE_URL"])
    databaseUrl = 'postgresql+psycopg2://{username}:{password}@{host}:{port}/{database}'
    engine = create_engine(databaseUrl.format(username=DBURL.username, password=DBURL.password,
                                              host=DBURL.hostname, port=DBURL.port,
                                              database=DBURL.path[1:]), echo=True)

except KeyError:
    # You could set url as below if you are using postgresql:
    # postgresql+psycopg2://root:root@localhost/ouija2
    engine = create_engine('mysql+mysqldb://root:root@localhost/ouija', echo=True)


Session = sessionmaker(engine)

session = Session()
