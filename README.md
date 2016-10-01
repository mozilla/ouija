ouija
=====

Failure rate analysis for treeherder.

# Installation

The production ouija server is running on Ubuntu, so this is probably the easiest environment in which to get things running, but other distributions of linux should be fine as well. We use Apache on the production server, but Ouija will run standalone for testing as well.
The master branch is running on http://seta-dev.herokuapp.com which located on heroku and depend on postgresql.

## Dependencies:

### System Dependencies

* MySQL/Postgresql
* Python

### Python Dependencies

* Flask
* MarkupSafe
* psycopg2
* MySQL-python
* sqlalchemy
* argparse
* requests
* redo
* If you use virtualenv or not you can install python dependencies with pip install -r requirements.txt

## Database configuration:
Ouija assumes MySQL has been installed with a root user using the password 'root'. And create a database named ouija first. You could create all database setup by running:

    Python database/models.py


Before you fetch job data into local environment, maybe you need to runnablejobs.json to help seta(a part of ouija) recognize all runnable jobs on treeherder, and you could get it by running:

    Python tools/update_runnablejobs.py

Fetch data for the database using the src/updatedb.py script. The delta argument controls how many days worth of data need to be fetched. Two should be sufficient to get started.

    python updatedb.py --delta 2

## Start the app
Start the application:

    cd src
    python server.py

You should see ouija running at http://localhost:8157/index.html.
