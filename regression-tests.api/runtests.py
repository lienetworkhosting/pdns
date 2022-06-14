#!/usr/bin/env python
#
# Shell-script style.

from __future__ import print_function
import os
import requests
from requests.exceptions import HTTPError
import shutil
import subprocess
import sys
import tempfile
import time

try:
  raw_input
except NameError:
  raw_input = input

MYSQL_DB='pdnsapi'
MYSQL_USER='root'
MYSQL_HOST=os.environ.get('MYSQL_HOST', 'localhost')
MYSQL_PASSWD=''

PGSQL_DB='pdnsapi'

SQLITE_DB = 'pdns.sqlite3'

LMDB_DB = 'pdns.lmdb'

WEBPORT = 5556
DNSPORT = 5300
APIKEY = '1234567890abcdefghijklmnopq-key'
WEBPASSWORD = 'something'
PDNSUTIL_CMD = [os.environ.get("PDNSUTIL", "../pdns/pdnsutil"), "--config-dir=."]

ZONES = ["example.com", "powerdnssec.org", "cryptokeys.org"]
ZONE_DIR = "../regression-tests/zones/"

AUTH_MYSQL_TPL = """
# Generated by runtests.py
launch=gmysql
gmysql-dnssec=on
gmysql-dbname="""+MYSQL_DB+"""
gmysql-user="""+MYSQL_USER+"""
gmysql-host="""+MYSQL_HOST+"""
gmysql-password="""+MYSQL_PASSWD+"""
"""

AUTH_PGSQL_TPL = """
# Generated by runtests.py
launch=gpgsql
gpgsql-dnssec=on
gpgsql-dbname="""+PGSQL_DB+"""
# on conflict is available in pg 9.5 and up
gpgsql-set-tsig-key-query=insert into tsigkeys (name,algorithm,secret) values($1,$2,$3) on conflict(name, algorithm) do update set secret=Excluded.secret
"""

AUTH_SQLITE_TPL = """
# Generated by runtests.py
launch=gsqlite3
gsqlite3-dnssec=on
gsqlite3-database="""+SQLITE_DB+"""
"""

AUTH_LMDB_TPL = """
# Generated by runtests.py
launch=lmdb
lmdb-filename="""+LMDB_DB+"""
"""

AUTH_COMMON_TPL = """
module-dir=../regression-tests/modules
default-soa-edit=INCEPTION-INCREMENT
launch+=bind
bind-config=bindbackend.conf
loglevel=5
"""

BINDBACKEND_CONF_TPL = """
# Generated by runtests.py
"""

ACL_LIST_TPL = """
# Generated by runtests.py
# local host
127.0.0.1
::1
"""

ACL_NOTIFY_LIST_TPL = """
# Generated by runtests.py
# local host
127.0.0.1
::1
"""

REC_EXAMPLE_COM_CONF_TPL = """
# Generated by runtests.py
auth-zones+=example.com=../regression-tests/zones/example.com
"""

REC_CONF_TPL = """
# Generated by runtests.py
auth-zones=
forward-zones=
forward-zones-recurse=
allow-from-file=acl.list
allow-notify-from-file=acl-notify.list
api-config-dir=%(conf_dir)s
include-dir=%(conf_dir)s
"""


def ensure_empty_dir(name):
    if os.path.exists(name):
        shutil.rmtree(name)
    os.mkdir(name)


def format_call_args(cmd):
    return "$ '%s'" % ("' '".join(cmd))


def run_check_call(cmd, *args, **kwargs):
    print(format_call_args(cmd))
    subprocess.check_call(cmd, *args, **kwargs)


wait = ('--wait' in sys.argv)
if wait:
    sys.argv.remove('--wait')

tests = [opt for opt in sys.argv if opt.startswith('--tests=')]
if tests:
    for opt in tests:
        sys.argv.remove(opt)
tests = [opt.split('=', 1)[1] for opt in tests]

daemon = (len(sys.argv) >= 2) and sys.argv[1] or None
backend = (len(sys.argv) == 3) and sys.argv[2] or 'gsqlite3'

if daemon not in ('authoritative', 'recursor') or backend not in ('gmysql', 'gpgsql', 'gsqlite3', 'lmdb'):
    print("Usage: ./runtests (authoritative|recursor) [gmysql|gpgsql|gsqlite3|lmdb]")
    sys.exit(2)

daemon = sys.argv[1]

pdns_server = os.environ.get("PDNSSERVER", "../pdns/pdns_server")
pdns_recursor = os.environ.get("PDNSRECURSOR", "../pdns/recursordist/pdns_recursor")
common_args = [
    "--daemon=no", "--socket-dir=.", "--config-dir=.",
    "--local-address=127.0.0.1", "--local-port="+str(DNSPORT),
    "--webserver=yes", "--webserver-port="+str(WEBPORT), "--webserver-address=127.0.0.1",
    "--webserver-password="+WEBPASSWORD,
    "--api-key="+APIKEY
]

# Take sdig if it exists (recursor in travis), otherwise build it from Authoritative source.
sdig = os.environ.get("SDIG", "")
if sdig:
    sdig = os.path.abspath(sdig)
if not sdig or not os.path.exists(sdig):
    run_check_call(["make", "-C", "../pdns", "sdig"])
    sdig = "../pdns/sdig"


if daemon == 'authoritative':
    zone2sql = os.environ.get("ZONE2SQL", "../pdns/zone2sql")

    # Prepare mysql DB with some zones.
    if backend == 'gmysql':
        subprocess.call(["mysqladmin", "--user=" + MYSQL_USER, "--password=" + MYSQL_PASSWD, "--host=" + MYSQL_HOST, "--force", "drop", MYSQL_DB])

        run_check_call(["mysqladmin", "--user=" + MYSQL_USER, "--password=" + MYSQL_PASSWD, "--host=" + MYSQL_HOST, "create", MYSQL_DB])

        with open('../modules/gmysqlbackend/schema.mysql.sql', 'r') as schema_file:
            run_check_call(["mysql", "--user=" + MYSQL_USER, "--password=" + MYSQL_PASSWD, "--host=" + MYSQL_HOST, MYSQL_DB], stdin=schema_file)

        with open('pdns.conf', 'w') as pdns_conf:
            pdns_conf.write(AUTH_MYSQL_TPL + AUTH_COMMON_TPL)

    # Prepare pgsql DB with some zones.
    elif backend == 'gpgsql':
        subprocess.call(["dropdb", PGSQL_DB])

        subprocess.check_call(["createdb", PGSQL_DB])

        with open('../modules/gpgsqlbackend/schema.pgsql.sql', 'r') as schema_file:
            subprocess.check_call(["psql", PGSQL_DB], stdin=schema_file)

        with open('pdns.conf', 'w') as pdns_conf:
            pdns_conf.write(AUTH_PGSQL_TPL + AUTH_COMMON_TPL)

    # Prepare sqlite DB with some zones.
    elif backend == 'gsqlite3':
        subprocess.call("rm -f " + SQLITE_DB + "*", shell=True)

        with open('../modules/gsqlite3backend/schema.sqlite3.sql', 'r') as schema_file:
            run_check_call(["sqlite3", SQLITE_DB], stdin=schema_file)

        with open('pdns.conf', 'w') as pdns_conf:
            pdns_conf.write(AUTH_SQLITE_TPL + AUTH_COMMON_TPL)

    # Prepare lmdb DB with some zones.
    elif backend == 'lmdb':
        subprocess.call("rm -f " + LMDB_DB + "*", shell=True)

        with open('pdns.conf', 'w') as pdns_conf:
            pdns_conf.write(AUTH_LMDB_TPL + AUTH_COMMON_TPL)

    with open('bindbackend.conf', 'w') as bindbackend_conf:
        bindbackend_conf.write(BINDBACKEND_CONF_TPL)

    for zone in ZONES:
        run_check_call(PDNSUTIL_CMD + ["load-zone", zone, ZONE_DIR+zone])

    run_check_call(PDNSUTIL_CMD + ["secure-zone", "powerdnssec.org"])
    servercmd = [pdns_server] + common_args + ["--no-shuffle", "--dnsupdate=yes", "--cache-ttl=0", "--api=yes"]

else:
    conf_dir = 'rec-conf.d'
    ensure_empty_dir(conf_dir)
    with open('acl.list', 'w') as acl_list:
        acl_list.write(ACL_LIST_TPL)
    with open('acl-notify.list', 'w') as acl_notify_list:
        acl_notify_list.write(ACL_NOTIFY_LIST_TPL)
    with open('recursor.conf', 'w') as recursor_conf:
        recursor_conf.write(REC_CONF_TPL % locals())
    with open(conf_dir+'/example.com..conf', 'w') as conf_file:
        conf_file.write(REC_EXAMPLE_COM_CONF_TPL)

    servercmd = [pdns_recursor] + common_args


# Now run pdns and the tests.
print("Launching server...")
print(format_call_args(servercmd))
serverproc = subprocess.Popen(servercmd, close_fds=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

print("Waiting for webserver port to become available...")
available = False
time.sleep(1)
for try_number in range(0, 10):
    try:
        res = requests.get('http://127.0.0.1:%s/' % WEBPORT)
        available = True
        break
    except HTTPError as http_err:
      print(f'HTTP error occurred: {http_err}')
    except Exception as err:
      print(f'Other error occurred: {err}')
    time.sleep(1)

if not available:
    print("Webserver port not reachable after 10 tries, giving up.")
    serverproc.terminate()
    serverproc.wait()
    print("==STDOUT===")
    print(proc.stdout.read())
    print("==STDERRR===")
    print(proc.stderr.read())
    sys.exit(2)

print("Query for example.com/A to create statistic data...")
run_check_call([sdig, "127.0.0.1", str(DNSPORT), "example.com", "A"])

print("Running tests...")
returncode = 0
test_env = {}
test_env.update(os.environ)
test_env.update({
    'WEBPASSWORD': WEBPASSWORD,
    'WEBPORT': str(WEBPORT),
    'APIKEY': APIKEY,
    'DAEMON': daemon,
    'BACKEND': backend,
    'MYSQL_DB': MYSQL_DB,
    'MYSQL_USER': MYSQL_USER,
    'MYSQL_HOST': MYSQL_HOST,
    'MYSQL_PASSWD': MYSQL_PASSWD,
    'PGSQL_DB': PGSQL_DB,
    'SQLITE_DB': SQLITE_DB,
    'LMDB_DB': LMDB_DB,
    'PDNSUTIL_CMD': ' '.join(PDNSUTIL_CMD),
    'SDIG': sdig,
    'DNSPORT': str(DNSPORT)
})

try:
    print("")
    run_check_call(["nosetests", "--with-xunit", "-v"] + tests, env=test_env)
except subprocess.CalledProcessError as ex:
    returncode = ex.returncode
finally:
    if wait:
        print("Waiting as requested, press ENTER to stop.")
        raw_input()
    serverproc.terminate()
    serverproc.wait()
    print("==STDOUT===")
    print(serverproc.stdout.read())
    print("==STDERRR===")
    print(serverproc.stderr.read())

sys.exit(returncode)
