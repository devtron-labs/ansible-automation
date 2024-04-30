from flask import Flask, request
import ansible_runner
import shutil
import os
import datetime
import psycopg2
import logging

CURR_PATH = os.getcwd()
tomcat_service_file = f"{CURR_PATH}/ansible/tomcat.service"

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

conn = psycopg2.connect(
    host="127.0.0.1",
    database="ansible",
    user=os.environ["DB_USERNAME"],
    password=os.environ["DB_PASSWORD"],
)

db = conn.cursor()

try:
    db.execute('CREATE TABLE IF NOT EXISTS logs (id serial PRIMARY KEY, host varchar (32)NOT NULL, date_time timestamptz NOT NULL, log_file varchar(512));')
    conn.commit()

except Exception as e:
    logger.error(e)
    
app = Flask(__name__)

def addEntryToDB(host,date_time,log_file_link):
    try:
        sql = "INSERT INTO logs(host, date_time, log_file) VALUES (%s, %s, %s)"
        db.execute(sql, (host, date_time, log_file_link))
        conn.commit()
    except Exception as e:
        logger.error(e)

def addLogToS3(log_file_path):
    pass


def getWarFileName(url):
    try:
        parts = url.split("/")
        file_name = parts[-1].split(".war")[0]
        return file_name
    except Exception as e:
        logger.error(e)
        return ""


def getNginxConf(hostname, warfile):
    conf = """
    server {
    listen 80 default_server;
    server_name %s;

    location / {
        proxy_pass http://localhost:8080/%s/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
    """ % (
        hostname,
        warfile,
    )
    return conf


@app.route("/")
def hello_world():
    return "Service is up and running."


@app.route("/deploy", methods=["POST"])
def deploy():
    try:
        body = request.json
        if not "host" in body:
            return "[host] is needed (IP Address of server).", 400
        if not "password" in body:
            return "[password] is needed of root user.", 400
        if not "war" in body:
            return "[war] is needed (War file to be deployed).", 400

        dateTime = str(datetime.datetime.now().isoformat())
        curr_execution = f'{CURR_PATH}/executions/{body["host"]}/{dateTime}'
        os.makedirs(curr_execution)

        nginx_conf_file = f"{curr_execution}/nginx.conf"
        with open(nginx_conf_file, "w") as file:
            file.write(getNginxConf(body["host"], getWarFileName(body["war"])))

        vars = {
            "ansible_ssh_pass": body["password"],
            "host": body["host"],
            "war_file_link": body["war"],
            "tomcat_service_file": tomcat_service_file,
            "nginx_conf_file": nginx_conf_file,
            "war_file_name": getWarFileName(body["war"]),
        }

        if vars["war_file_name"] == "":
            return "[war] should be war file link similar to https://github.com/raunit-verma/war/raw/main/devtron.war"

        # copy ansible playbook
        shutil.copy(f"{CURR_PATH}/ansible/deploy_war.yaml", curr_execution)

        # create hosts.ini file
        hosts_file = f"{curr_execution}/hosts.ini"
        with open(hosts_file, "w") as file:
            file.write(body["host"])

        # create ansible.cfg
        ansible_cfg = f"{curr_execution}/ansible.cfg"

        with open(ansible_cfg, "w") as file:
            file.write(f"[defaults]\nlog_path={curr_execution}/ansible.log")

        # create logs file
        with open(f"{curr_execution}/ansible.log", "w") as file:
            pass

        # r = ansible_runner.run(
        #     private_data_dir=curr_execution,
        #     playbook=f"{curr_execution}/deploy_war.yaml",
        #     inventory=f"{curr_execution}/hosts.ini",
        #     extravars=vars,
        #     verbosity=2,
        #     quiet=True,
        # )

        # if r.status == "successful":
            addEntryToDB(body['host'],dateTime,"temp file link")
            return "Completed Successfully"

        return "Process failed. Please see the logs to debug."
    except Exception as e:
        logger.error(e)
        return "Internal Server Error", 500


if __name__ == "__main__":
    app.run()
