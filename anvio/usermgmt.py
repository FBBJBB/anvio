# -*- coding: utf-8
"""
    user management db operations.
"""

import os
import sqlite3

import copy
import crypt
import string
import random
import hashlib
import shutil
import re

import time
from datetime import date

import anvio
import anvio.terminal as terminal
import anvio.interactive as interactive
import anvio.filesnpaths as filesnpaths

from anvio.errors import ConfigError


__author__ = "Tobias Paczian"
__copyright__ = "Copyright 2015, The anvio Project"
__credits__ = []
__license__ = "GPL 3.0"
__version__ = anvio.__version__
__maintainer__ = "Tobias Paczian"
__email__ = "tobiaspaczian@googlemail.com"
__status__ = "Development"


run = terminal.Run()
progress = terminal.Progress()


class UserMGMT:
    def __init__(self, args, client_version, ignore_version=False, mailer = None,
                 run = run, progress = progress):
        self.args = args
        self.run = run
        self.progress = progress

        self.users_data_dir = args.users_data_dir
        self.users_db_path = os.path.join(self.users_data_dir, 'USERS.db')
        self.mailer = mailer

        self.version = None

        if not os.path.exists(self.users_data_dir):
            self.run.warning('A new directory is being initiated to hold users database ...')
            filesnpaths.gen_output_directory(self.users_data_dir)
            self.create_self(client_version)

        if not os.path.exists(self.users_db_path):
            self.run.warning('An empty users database is being initiated in an already existing directory ...')
            self.create_self(client_version)

        self.conn = sqlite3.connect(self.users_db_path)
        self.conn.text_factory = str
        self.conn.row_factory = dict_factory

        self.cursor = self.conn.cursor()

        self.version = self.get_version()

        if str(self.version) != str(client_version) and not ignore_version:
            raise ConfigError, "It seems the database '%s' was generated when your client was at version %s,\
                                however, your client now is at version %s. Which means this database file\
                                cannot be used with this client anymore and needs to be upgraded to the\
                                version %s :/"\
                                        % (self.users_db_path, self.version, client_version, client_version)


    def get_version(self):
        try:
            return self.get_meta_value('version')
        except Exception, e:
            raise ConfigError, "%s does not seem to be a database generated by anvi'o :/ Here is the original\
                                complaint: '%s'," % (self.users_db_path, e)


    def create_self(self, client_version):
        conn = sqlite3.connect(self.users_db_path)
        cursor = conn.cursor()

        cursor.execute("CREATE TABLE self (key TEXT PRIMARY KEY, value TEXT)")
        cursor.execute("CREATE TABLE users (login TEXT PRIMARY KEY, firstname TEXT, lastname TEXT, email TEXT, password TEXT, path TEXT, token TEXT, accepted INTEGER, project TEXT, affiliation TEXT, ip TEXT, clearance TEXT, date TEXT)")
        cursor.execute("CREATE TABLE projects (name TEXT PRIMARY KEY, path TEXT, user TEXT)")
        cursor.execute("CREATE TABLE views (name TEXT PRIMARY KEY, project TEXT, public INTEGER, token TEXT)")
        cursor.execute("INSERT INTO self VALUES(?,?)", ('version', client_version,))

        conn.commit()
        conn.close()


    def remove_meta_key_value_pair(self, key):
        p = (key, )
        self.cursor.execute("DELETE FROM self WHERE key=?", p)
        self.conn.commit()


    def get_meta_value(self, key):
        p = (key, )
        response = self.cursor.execute("SELECT value FROM self WHERE key=?", p)
        row = response.fetchone()
        
        if not row:
            raise ConfigError, "A value for '%s' does not seem to be set in table 'self'." % key

        val = row['value']

        if type(val) == type(None):
            return None

        try:
            val = int(val)
        except ValueError:
            pass

        return val

    def disconnect(self):
        self.conn.close()


    ######################################
    # USERS
    ######################################

    # adds project information and removes sensitive data from the user struct
    def complete_user(self, user, internal=False):
        if not user:
            raise ConfigError, "complete_user called without user"

        if user['project']:
            p = (user['login'], user['project'], )
            response = self.cursor.execute("SELECT * FROM projects WHERE user=? AND name=?", p)
            project = response.fetchone()
            if project:
                user['project'] = project['name']
                user['project_path'] = project['path']
            else:
                user['project'] = None
                user['project_path'] = None

        # get all user project names
        p = (user['login'], )
        response = self.cursor.execute("SELECT name FROM projects WHERE user=?", p)
        projects = response.fetchall()
        ps = []
        for row in projects:
            ps.append({ "name": row['name'], "views": []})
            p = (row['name'], )
            response = self.cursor.execute("SELECT name, public, token FROM views WHERE project=?", p)
            views = response.fetchall()
            for r in views:
                ps[len(ps) - 1]['views'].append({"name": r['name'], "public": r['public'], "token": r['token']});
        user['projects'] = ps

        # remove sensitive data
        if not internal:
            del user['password']
        
        return user

    
    def create_user(self, firstname, lastname, email, login, password, affiliation, ip, clearance="user"):
        # check if all arguments were passed
        if not (firstname and lastname and email and login and password):
            return { 'status': 'error', 'message': "You must pass a firstname, lastname, email login and password to create a user", 'data': None }

        # check if the login name is already taken
        p = (login, )
        response = self.cursor.execute('SELECT login FROM users WHERE login=?', p)
        row = response.fetchone()

        if row:
            return { 'status': 'error', 'message': "Login '%s' is already taken." % login, 'data': None }

        # check if the email is already taken
        p = (email, )
        response = self.cursor.execute('SELECT email FROM users WHERE email=?', p)
        row = response.fetchone()

        if row:
            return { 'status': 'error', 'message': "Email '%s' is already taken." % email, 'data': None }
        
        # calculate path
        path = hashlib.md5(login).hexdigest()

        # crypt password
        password = crypt.crypt(password, ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(2)))

        # generate token
        token = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(32))

        # set accepted to 'false'
        accepted = 0

        # get the current date
        entrydate = date.fromtimestamp(time.time()).isoformat()
        
        # create the user entry in the DB
        p = (firstname, lastname, email, login, password, path, token, accepted, affiliation, ip, clearance, entrydate, )
        response = self.cursor.execute("INSERT INTO users (firstname, lastname, email, login, password, path, token, accepted, affiliation, ip, clearance, date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", p)
        self.conn.commit()

        anvioURL = "http://%s/" % self.args.ip_address if self.args.ip_address else "localhost";
        if self.mailer:
            # send the user a mail to verify the email account
            messageSubject = "anvio account request"
            messageText = "You have requested an account for anvio.\n\nClick the following link to activate your account:\n\n"+anvioURL+"confirm?code="+token+"&login="+login;

            self.mailer.send(email, messageSubject, messageText)
            return { 'status': 'ok', 'message': "User request created", 'data': None }
        else:
            if self.args.validate_users_automatically:
                # because there is no SMTP configuration, we will just go ahead and validate the user.
                self.run.info_single('A new user, "%s", has been created (and validated automatically).' % login)
                return self.accept_user(login, token)
            else:
                return { 'status': 'warning', 'message': "There is no smtp configuration and automatic user validation is disabled. User %s cannot be created" % login, 'data': None }


    def get_user_for_email(self, email):
        if not email:
            return { 'status': 'error', 'message': "You must pass an email to retrieve a user entry", 'data': None }

        p = (email, )
        response = self.cursor.execute("SELECT * FROM users WHERE email=?", p)
        user = response.fetchone()

        if user:
            # check if the user has a project set
            user = self.complete_user(user)
        
        return { 'status': 'ok', 'message': None, 'data': user }
    

    def get_user_for_login(self, login, internal=False):
        if not login:
            return { 'status': 'error', 'message': "You must pass a login to retrieve a user entry", 'data': None }

        p = (login, )
        response = self.cursor.execute("SELECT * FROM users WHERE login=?", p)
        user = response.fetchone()

        if user:
            # check if the user has a token
            if not user['token']:
                token = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(32))
                token = user['login'] + token
                p = (token, user['login'], )
                self.cursor.execute("UPDATE users SET token=? WHERE login=?", p)
                self.conn.commit()
                user['token'] = token
                
            # check if the user has a project set
            user = self.complete_user(user, internal)
        
            return { 'status': 'ok', 'message': None, 'data': user }
        else:
            return { 'status': 'error', 'message': "User not found for login %s" % login, 'data': None }

    def get_user_for_token(self, token):
        if not token:
            return { 'status': 'error', 'message': "You must pass a token to retrieve a user entry", 'data': None }

        p = (token, )
        response = self.cursor.execute("SELECT * FROM users WHERE token=?", p)
        user = response.fetchone()

        if user:
            # check if the user has a project set
            user = self.complete_user(user)
            
            return { 'status': 'ok', 'message': None, 'data': user }
        else:
            return { 'status': 'ok', 'message': "invalid token", 'data': None }


    def reset_password(self, user):
        if not user:
            return { 'status': 'error', 'message': "You must pass a user to reset a password", 'data': None }

        if user.has_key('status'):
            if user['status'] == 'ok':
                user = user['data']
            else:
                return user
        
        # generate random password
        password = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(8))

        # crypt password
        cpassword = crypt.crypt(password, ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(2)))

        login = user['login']
        
        # update the user entry in the DB
        p = (cpassword, login)
        response = self.cursor.execute("UPDATE users SET password=? WHERE login=?", p)
        self.conn.commit()

        # send the user a mail with the new password
        email = user['email']
        messageSubject = "anvio password reset"
        messageText = "You have requested your password for your anvi'o account to be reset.\n\nYour new password is:\n\n"+password+"\n\nPlease log into anvi'o with these credentials and change your password.";

        self.mailer.send(email, messageSubject, messageText)

        return { 'status': 'ok', 'message': "User password reset, message sent to %s" % email, 'data': None }

    def change_password(self, user, password):
        if not user:
            return { 'status': 'error', 'message': "You must pass a user to change a password", 'data': None }

        if not password:
            return { 'status': 'error', 'message': "You must select a password", 'data': None }

        if user.has_key('status'):
            if user['status'] == 'ok':
                user = user['data']
            else:
                return user
        
        # crypt password
        cpassword = crypt.crypt(password, ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(2)))

        login = user['login']
        
        # update the user entry in the DB
        p = (cpassword, login)
        response = self.cursor.execute("UPDATE users SET password=? WHERE login=?", p)
        self.conn.commit()

        return { 'status': 'ok', 'message': "New password set", 'data': None }
        
    def accept_user(self, user, token):
        if not user:
            return { 'status': 'error', 'message': "You must pass a user to accept", 'data': None }

        if not token:
            return { 'status': 'error', 'message': "You must pass a token to accept a user", 'data': None }

        if user.has_key('status'):
            if user['status'] == 'ok':
                user = user['data']
            else:
                return user
        
        if user['token'] == token:
            self.cursor.execute("UPDATE users SET accepted=1 WHERE login=?", p)
            self.conn.commit()

            # create the user directory
            path = self.users_data_dir + '/userdata/' + user['path']
            if not os.path.exists(path):
                os.makedirs(path)

            return { 'status': 'ok', 'message': "User confirmed", 'data': None }
        else:
            return { 'status': 'error', 'message': "Invalid token for user '%s'." % user['login'], 'data': None }


    def login_user(self, login, password):
        if not login:
            return { 'status': 'error', 'message': "You must pass a login", 'data': None }

        if not password:
            return { 'status': 'error', 'message': "You must pass a password", 'data': None }
        
        # get the user from the db
        user = self.get_user_for_login(login, True)
        if user['status'] == 'ok':
            user = user['data']
        else:
            user = None

        if not user:
            return { 'status': 'error', 'message': "Login or password invalid", 'data': None }

        # verify the password
        valid = crypt.crypt(password, user['password']) == user['password']

        if not valid:
            return { 'status': 'error', 'message': "Login or password invalid", 'data': None }

        # generate a new token
        token = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(32))
        token = login + token
        p = (token, login, )
        self.cursor.execute("UPDATE users SET token=? WHERE login=?", p)
        self.conn.commit()

        # check if the user has a project set
        user = self.complete_user(user)

        # set the user token
        user["token"] = token

        return { 'status': 'ok', 'message': "Login successful", 'data': user }

    def logout_user(self, login):
        if not login:
            return { 'status': 'error', 'message': "You must pass a login to log out a user", 'data': None }

        # get the user from the db
        user = self.get_user_for_login(login)
        if user['status'] == 'ok':
            user = user['data']
        else:
            user = None

        if not user:
            return { 'status': 'error', 'message': "user not found", 'data': None }

        # remove the token from the DB
        p = (login, )
        self.cursor.execute("UPDATE users SET token='' WHERE login=?", p)
        self.conn.commit()

        return { 'status': 'ok', 'message': "User %s logged out" % login, 'data': None }

    def user_list(self, offset=0, limit=25, order='lastname', dir='ASC', filter={}):
        filterwords = []
        for field in filter.keys():
            filterwords.append(field+" LIKE '"+filter[field].replace("\\","\\\\").replace("'", "\'")+"'")

        where_phrase = ""
        if len(filterwords):
            where_phrase = " WHERE "+" AND ".join(filterwords)

        select = "SELECT users.*, COUNT(projects.name) AS projects FROM users LEFT OUTER JOIN projects ON users.login=projects.user"+where_phrase+" GROUP BY users.login ORDER BY "+order+" "+dir+" LIMIT "+str(limit)+" OFFSET "+str(offset)
        response = self.cursor.execute(select)
        table = response.fetchall()

        for row in table:
            del row['password']
            del row['path']
            del row['token']

        select = "SELECT COUNT(*) AS num FROM users "+where_phrase
        response = self.cursor.execute(select)
        count = response.fetchone()

        data = { "limit": limit, "offset": offset, "total": count['num'], "data": table, "order": order, "dir": dir, "filter": filter }
        
        return { 'status': 'ok', 'message': None, 'data': data }

    ######################################
    # PROJECTS
    ######################################
    
    def create_project(self, user, pname):
        if not user:
            return { 'status': 'error', 'message': "You must pass a user to create a project", 'data': None }
        if not pname:
            return { 'status': 'error', 'message': "You must pass a project name to create a project", 'data': None }

        if user.has_key('status'):
            if user['status'] == 'ok':
                user = user['data']
            else:
                return user
        
        # create a path name for the project
        ppath = hashlib.md5(pname).hexdigest()
        path = self.users_data_dir + '/userdata/' + user["path"] + '/' + ppath

        if not os.path.exists(path):
            os.makedirs(path)
            p = (pname, ppath, login, )
            response = self.cursor.execute("INSERT INTO projects (name, path, user) VALUES (?, ?, ?)", p)
            self.conn.commit()
            return { 'status': 'ok', 'message': None, 'data': { "name": pname, "path": ppath, "user": user['login'] } }
        else:
            return { 'status': 'error', 'message': "You already have a project of that name", 'data': None }

        
    def get_project(self, user, projectname):
        if not user:
            return { 'status': 'error', 'message': "You must pass a user to retrieve a project", 'data': None }

        if not projectname:
            return { 'status': 'error', 'message': "You must pass a project name", 'data': None }

        if user.has_key('status'):
            if user['status'] == 'ok':
                user = user['data']
            else:
                return user
        
        p = (user, projectname, )
        response = self.cursor.execute("SELECT * FROM projects WHERE user=? AND name=?", p)
        project = response.fetchone()

        return { 'status': 'ok', 'message': None, 'data': project }
        

    def set_project(self, user, pname):
        if not user:
            return { 'status': 'error', 'message': "You must pass a user to create a project", 'data': None }
        if not pname:
            return { 'status': 'error', 'message': "You must pass a project name to create a project", 'data': None }

        if user.has_key('status'):
            if user['status'] == 'ok':
                user = user['data']
            else:
                return user

        p = (user['login'], pname, )
        response = self.cursor.execute("SELECT * FROM projects WHERE user=? AND name=?", p)
        row = response.fetchone()
        
        if row:
            p = (pname, user['login'], )
            self.cursor.execute("UPDATE users SET project=? WHERE login=?", p)
            self.conn.commit()
            return { 'status': 'ok', 'message': "project set", 'data': None }
        else:
            return { 'status': 'ok', 'message': "the user does not own this project", 'data': None }


    def delete_project(self, user, pname):
        if not user:
            return { 'status': 'error', 'message': "You must pass a user to create a project", 'data': None }
        if not pname:
            return { 'status': 'error', 'message': "You must pass a project name to create a project", 'data': None }

        if user.has_key('status'):
            if user['status'] == 'ok':
                user = user['data']
            else:
                return user
        
        # create a path name for the project
        ppath = hashlib.md5(pname).hexdigest()
        path = self.users_data_dir + '/userdata/'+ user["path"] + '/' + ppath
        
        p = (user['login'], pname, )
        response = self.cursor.execute("SELECT * FROM projects WHERE user=? AND name=?", p)
        row = response.fetchone()
        
        if row:
            p = (None, user['login'], )
            self.cursor.execute("UPDATE users SET project=? WHERE login=?", p)
            p = (user['login'], pname, )
            self.cursor.execute("DELETE FROM projects WHERE user=? AND name=? ", p)
            self.conn.commit()
            p = (pname, )
            self.cursor.execute("DELETE FROM views WHERE project=? ", p)
            self.conn.commit()

            if os.path.exists(path):
                shutil.rmtree(path, ignore_errors=True)
            
            return { 'status': 'ok', 'message': "project deleted", 'data': None }
        else:
            return { 'status': 'error', 'message': "the user does not own this project", 'data': None }
        

    ######################################
    # VIEWS
    ######################################
    def get_view(self, vname, token=None):
        # get the view
        p = (vname, )
        response = self.cursor.execute("SELECT * FROM views WHERE name=?", p)
        view = response.fetchone()
        if not view:
            return { 'status': 'error', 'message': "a view with name %s does not exist" % vname, 'data': None }

        # get the project for this view
        p = (view['project'], )
        response = self.cursor.execute("SELECT * FROM projects WHERE name=?", p)
        row = response.fetchone()
        if row:           
            # create the path and add it to the return structure
            path = row['path']
            
            # get the user of the project
            user = self.get_user_for_login(row['user'])
            if user['status'] == 'ok':
                user = user['data']
            else:
                user = None

            if not user:
                return { 'status': 'error', 'message': "Could not find a user for project %s" % view['project'], 'data': None }
            
            view['path'] = user['path'] + '/' + path
        else:
            # the project is gone, clean up this reference
            p = (vname, )
            response = self.cursor.execute("DELETE FROM views WHERE name=?", p)
            self.conn.commit()

            return { 'status': 'error', 'message': "the project for this view no longer exists", 'data': None }

        # check if we have a token and if so see if it matches
        if token:
            if view['token'] == token:
                return { 'status': 'ok', 'message': None, 'data': view }
            else:
                return { 'status': 'error', 'message': "invalid token", 'data': None }

        # otherwise check if the view is public
        if view['public'] == 1:
            return { 'status': 'ok', 'message': None, 'data': view }
        else:
            return { 'status': 'error', 'message': "a token is required to access this view", 'data': None }


    def delete_view(self, user, vname):
        if not user:
            return { 'status': 'error', 'message': "You must provide a user to delete a view", 'data': None }

        if user.has_key('status'):
            if user['status'] == 'ok':
                user = user['data']
            else:
                return user
        
        # get the view
        p = (vname, )
        response = self.cursor.execute("SELECT * FROM views WHERE name=?", p)
        row = response.fetchone()
        if not row:
            return { 'status': 'error', 'message': "a view with name %s does not exist" % vname, 'data': None }

        response = self.cursor.execute("DELETE FROM views WHERE name=?", p)
        self.conn.commit()

        return { 'status': 'ok', 'message': "view deleted", 'data': None }

    def create_view(self, user, vname, pname, public=1):
        if not user:
            return { 'status': 'error', 'message': "You must provide a user to create a view", 'data': None }

        if user.has_key('status'):
            if user['status'] == 'ok':
                user = user['data']
            else:
                return user
        
        # check if the view name is valid
        if not re.match("^[A-Za-z0-9_-]+$", vname):
            return { 'status': 'error', 'message': "Name contains invalid characters. Only letters, digits, dash and underscore are allowed.", 'data': None }

        # check if the view name is unique
        p = (vname, )
        response = self.cursor.execute("SELECT * FROM views WHERE name=?", p)
        row = response.fetchone()
        if row:
            return { 'status': 'error', 'message': "view name already taken", 'data': None }

        # check if the project is owned by the user
        p = (pname, login)
        response = self.cursor.execute("SELECT * FROM projects WHERE name=? AND user=?", p)
        row = response.fetchone()
        if not row:
            return { 'status': 'error', 'message': "The user does not own this project", 'data': None }

        # create a token
        token = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(32))
        
        # create the db entry
        p = (vname, pname, public, token, )
        response = self.cursor.execute("INSERT INTO views (name, project, public, token) values (?, ?, ?, ?)", p)
        self.conn.commit()

        return { 'status': 'ok', 'message': None, 'data': token }
    

    ######################################
    # REQUEST SECTION
    ######################################

    def check_user(self, request):
        # check if we have a cookie
        if request.get_cookie('anvioSession'):

            # we have a cookie, check if it is valid
            retval = self.get_user_for_token(request.get_cookie('anvioSession'))
            if retval['status'] == 'ok':
                user = retval['data']
                if user.has_key('project_path'):
                    basepath = self.users_data_dir + '/userdata/' + user['path'] + '/' + user['project_path'] + '/'
                    args = copy.deepcopy(self.args)
                    args.tree = basepath + 'treeFile'
                    args.fasta_file = basepath + 'fastaFile'
                    args.view_data = basepath + 'dataFile'
                    args.title = user['project']
                    args.read_only = False
                    args.profile_db = basepath + 'profile.db'
                    args.samples_db = basepath + 'samples.db'
                    args.additional_layers = None
                    addFile = basepath + 'additionalFile'
                    if os.path.isfile(addFile):
                        args.additional_layers = addFile
                    
                    d = interactive.InputHandler(args)
                    return [ True, d, args ]
                else:
                    return [ False ]
            else:
                return [ False ]
        else:
            return [ False ]


    def check_view(self, request):
        if request.get_cookie('anvioView'):
            p = request.get_cookie('anvioView').split('|')
            retval = userdb.get_view(p[0], p[1])
            if retval[0]:
                args = self.args
                basepath = self.users_data_dir + '/userdata/' + retval[1]['path'] + '/'
                args.tree = basepath + 'treeFile'
                args.fasta_file = basepath + 'fastaFile'
                args.view_data = basepath + 'dataFile'
                args.title = retval[1]['project']
                args.read_only = True

                d = interactive.InputHandler(args)

                return [ True, d, args ]
            else:
                return [ False ]
        else:
            return [ False ]


    def set_user_data(self, request, data):
        retval = self.check_view(request)
        if retval[0]:
            return retval[1]
        retval = self.check_user(request)
        if retval[0]:
            return [ retval[1], retval[2] ]

        return [ data, self.orig_args ]

        
def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
            
    return d
