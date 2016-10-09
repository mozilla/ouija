ouija
=====

Failure rate analysis for treeherder.

# Installation

The production ouija server is running on Ubuntu, so this is probably the easiest environment in which to get things running, but other distributions of linux should be fine as well. We use Apache on the production server, but Ouija will run standalone for testing as well.

Heroku staging is running from the master branch (http://seta-dev.herokuapp.com).
Heroku production is running from the heroku branch (http://seta.herokuapp.com).
Both instances use PostgreSQL.

## Dependencies:

### System Dependencies

* MySQL/Postgresql
* Python

### Python Dependencies

Check requirements.txt for all Python dependencies.

## Database configuration:
Ouija assumes MySQL has been installed with a root user using the password 'root'. And create a database named '''ouija''' first.

Create all tables by running:

    python database/models.py


Before you can fetch jobs' data into your local environment you might need to runnablejobs.json to help SETA (part of ouija) recognize all runnable jobs on treeherder.
You can do this by running:

    python tools/update_runnablejobs.py

Fetch data for the database using the src/updatedb.py script. The delta argument controls how many days worth of data need to be fetched. Two should be sufficient to get started.

    python updatedb.py --delta 2

## Start the app
Start the application:

    cd src
    python server.py

You should see ouija running at http://localhost:8157/index.html.

## Troubleshooting
If your local mysql root user does not have a password you will not be able to use SETA properly. To set the password use this command:

    mysqladmin -u root password root

Otherwise you will see an error like this '''sqlalchemy.exc.OperationalError: (_mysql_exceptions.OperationalError) (1045, "Access denied for user 'root'@'localhost' (using password: YES)"'''
