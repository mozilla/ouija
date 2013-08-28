ouija
=====

Failure rate analysis for tbpl.

Installation

Dependencies:
* Apache
** libapache2-mod-wsgi
* MySQL
* Python
** python-mysqldb

1) Copy the apache configuration file from config/apache2/default to /etc/apache2/sites-available/default. Update the paths to be valid for your system.
2) Restart Apache.
3) Create the MySQL database using the sql/schema.sql script.
4) Run the src/updatedb.py to get initial data in your database.

