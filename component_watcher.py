#!/usr/bin/python3.9
import argparse
import datetime
import configparser
import time
import subprocess
import os
from threading import Thread, Event
from loguru import logger
from datadog import statsd
import psutil
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import socket
import boto3
import yaml
import requests
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
import json


class ComponentWatcher:
    def __init__(self, config_path):
        self.script_directory = os.path.dirname(os.path.abspath(__file__))
        # Hardcoded path for appconfig.yaml
        self.app_config_path = os.path.join(self.script_directory, './config/appconfig.yaml')

        # Load appconfig.yaml configuration
        self.config = self.load_app_config(self.app_config_path)

        # Mail Configurations
        self.fromaddr = self.config['mail_configs']['from_address']
        self.toaddr = self.config['mail_configs']['to_address']

        # Additional Configurations
        self.logs_size_send = self.config['logs_size_send']
        self.process_details_send = self.config['process_details_send']

        # AWS Secrets Manager settings
        secret_name = self.config['aws_secrets_manager']['secret_name']
        region_name = self.config['aws_secrets_manager']['region_name']

        # Fetch secrets from AWS Secrets Manager
        self.username, self.passswrd, self.smtp_server = self.get_secrets_from_aws(secret_name, region_name)

        self.interval = 20

        # Component-specific configuration file
        self.config_file_path = os.path.join(self.script_directory, config_path)
        self.parser = configparser.ConfigParser()
        self.parser.read(self.config_file_path)

        self.threads = {}
        self.stop_flags = {}
        self.max_up_days = {}
        self.latest_pid = {}
        self.last_pid = {}
        self.cache_max_up_days()

        # Set up logging
        log_file_path = os.path.join(self.script_directory, './logs/watcher_{time:YYYYMMDDHHmmss}.log')
        logger.add(
            log_file_path,
            rotation="1 day",  # Rotate log files daily
            retention="2 days",  # Retain log files for 2 days
            format=f"{{time:YYYY-MM-DD HH:mm:ss.SSS}} | {{level: <7}} | {{extra[comp_name]: <{self.get_max_length_of_component_name()}}} | {{message}}",
            level="DEBUG"
        )

    def load_app_config(self, app_config_path):
        """Load configurations from appconfig.yaml."""
        try:
            with open(app_config_path, 'r') as file:
                return yaml.safe_load(file)
        except FileNotFoundError:
            logger.error(f"Config file {app_config_path} not found.")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML file {app_config_path}: {e}")
            raise

    def get_secrets_from_aws(self, secret_name, region_name):
        """Fetch secrets from AWS Secrets Manager."""
        try:
            # Create a Secrets Manager client
            client = boto3.client(service_name='secretsmanager', region_name=region_name)

            # Retrieve the secret value
            get_secret_value_response = client.get_secret_value(SecretId=secret_name)

            # Parse the secret
            secret = get_secret_value_response['SecretString']
            secrets_dict = json.loads(secret)

            # Ensure required keys are present
            username = secrets_dict.get('USERNAME')
            password = secrets_dict.get('PASSWORD')
            smtp_server = secrets_dict.get('SMTP_SERVER')

            if not all([username, password, smtp_server]):
                raise ValueError("Required keys (USERNAME, PASSWORD, SMTP_SERVER) are missing in the secret.")

            return username, password, smtp_server

        except NoCredentialsError:
            logger.error("AWS credentials not found.")
        except PartialCredentialsError:
            logger.error("Incomplete AWS credentials.")
        except Exception as e:
            logger.error(f"Failed to retrieve secrets from AWS: {e}")
        return None, None, None


    def get_max_length_of_component_name(self):
        max_length = 0
        for id in self.parser.sections():
            name = self.parser[id]['name']
            name_length = len(name)
            if name_length > max_length:
                max_length = name_length
        return max_length
    
    def cache_max_up_days(self):
        for id in self.parser.sections():
            maxUpDays = 1
            if self.parser.has_option(id, 'maxUpDays'):
                maxUpDays = int(self.parser[id]['maxUpDays'])
            else:
                maxUpDays = 1
            self.max_up_days[id] = maxUpDays

    def get_day_names(self, runningDates):
        days_map = {
            '0': 'Sunday',
            '1': 'Monday',
            '2': 'Tuesday',
            '3': 'Wednesday',
            '4': 'Thursday',
            '5': 'Friday',
            '6': 'Saturday'
        }
        day_numbers = runningDates.strip('[]').split(',')
        day_names = [days_map[day.strip()] for day in day_numbers]
        return ', '.join(day_names)


    def mail_send(self, component_name: str, status: str, restart_status: bool, id: str):
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        msg = MIMEMultipart()
        msg['From'] = self.fromaddr
        msg['To'] = self.toaddr

        # Fetch additional component details from the config file
        tag = self.parser[id]['tag']
        runScriptPath = self.parser[id]['runScriptPath']
        startTime = self.parser[id]['startTime']
        endTime = self.parser[id]['endTime']
        runningDates = self.parser[id]['runningDates']
        
        if status == "down":
            subject = f"{component_name.upper()} COMPONENT IS DOWN"
            icon = "⚠️"
            message_color = "#FF6347"  # Red 
            message = f"{component_name.upper()} COMPONENT IS DOWN"
            if restart_status:
                status_message_color = "#4682B4"
                status_message = "Restarting in Progress......."
            else:
                status_message_color = "#FF6347" # Red
                status_message = "Restarting not configured. Please check manually."
        else:
            subject = f"{component_name.upper()} COMPONENT STARTED SUCCESSFULLY"
            icon = "✅"
            message_color = "#4CAF50"  # Green for success
            status_message_color = "#4CAF50" 
            message = f"{component_name.upper()} STARTED"
            status_message = "Everything is running smoothly!"

        msg['Subject'] = subject

        body = f"""
        <html>
            <head></head>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <div>
                    <h1 style="color: {message_color};">{icon} {message}</h1>
                    <p style="font-size: 18px; color: #333; font-family: 'Courier New', monospace; white-space: pre;">
                        component_name      = <strong>{component_name.upper()}</strong><br/>
                        server              = <strong>{hostname} ({ip_address})</strong><br/>
                        tag                 = <strong>{tag}</strong><br/>
                        run_script_path     = <strong>{runScriptPath}</strong><br/>
                        start_time          = <strong>{startTime}</strong><br/>
                        stop_time           = <strong>{endTime}</strong><br/>
                        running_dates       = <strong>{self.get_day_names(runningDates)}</strong><br/>
                    </p>
                    <p style="font-size: 18px; color: {status_message_color};">
                        {status_message}
                    </p>
                </div>
            </body>
        </html>
        """
    
        msg.attach(MIMEText(body, 'html'))

        server = smtplib.SMTP(self.smtp_server, 587)
        server.starttls()
        server.login(self.username, self.passswrd)
        text = msg.as_string()
        server.sendmail(self.fromaddr, self.toaddr, text)
        server.quit()



    def execute_command(self, command, logger_with_name, description="command"):
        try:
            output = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True)
            return output
        except Exception as e:
            logger_with_name.error(f"Failed to run {description}: {e}")
            return None

    def get_pid(self, id, logger_with_name):
        tag = self.parser[id]['tag']
        command = f"ps x | grep -aiw {tag} | grep -v grep"
        command_output = self.execute_command(command, logger_with_name, f"Process check for {tag}")
        pid = None
        if command_output:
            process_info = command_output.stdout.read().strip()
            pids = [int(line.split()[0]) for line in process_info.splitlines()]

            if len(pids) == 1:
                pid = pids[0] 
                self.last_pid[id] = pid
            elif len(pids) > 1:
                logger_with_name.warning(f"Multiple processes found for tag: {tag}. PIDs: {pids}")
                pid = self.last_pid.get(id)
        self.latest_pid[id] = pid
        return pid


    def process_checker(self, id, logger_with_name):
        pid = self.get_pid(id, logger_with_name)
        if pid:
            output = {'status': 'running', 'pid': pid}
        else:
            output = {'status': 'notRunning'}
        return output


    def port_staus_sender(self, id, logger_with_name):
        port = self.parser[id]['port']
        name = self.parser[id]['name']
        command = f"netstat -tulpn | grep -aiw {port} | grep -v grep | grep -aiw tcp | wc -l"
        command_output = self.execute_command(command, logger_with_name, f"Port check for {port}")
        if command_output:
            output = int(command_output.stdout.read().strip())
            if output == 1:
                statsd.service_check('feed.component.port.status', 0, tags=[f"component:{name}", f"port:{port}"])
            elif output == 0:
                statsd.service_check('feed.component.port.status', 2, tags=[f"component:{name}", f"port:{port}"])
        else:
            logger_with_name.error(f"Port Checker for {name} has been failed.")

    def process_details_sender(self, id):
        name = self.parser[id]['name']
        pid = self.latest_pid.get(id)

        if pid:
            try:
                process = psutil.Process(pid)
                start_time = datetime.datetime.fromtimestamp(process.create_time())
                uptime_seconds = int((datetime.datetime.now() - start_time).total_seconds())
                statsd.gauge('feed.component.process.up_time', uptime_seconds, tags=[f"component:{name}", f"pid:{pid}"])
                max_up_days = self.max_up_days.get(id)
                max_uptime_seconds =  max_up_days*86400
                statsd.gauge('feed.component.process.up_time.max', max_up_days, tags=[f"component:{name}"])
                if uptime_seconds > max_uptime_seconds:
                    statsd.gauge('feed.component.process.up_time.max.exceeded', 1, tags=[f"component:{name}", f"pid:{pid}"])
                else:
                    statsd.gauge('feed.component.process.up_time.max.exceeded', 0, tags=[f"component:{name}", f"pid:{pid}"])

                memory_info = process.memory_info()
                memory_used_mb = round(memory_info.rss / (1024 * 1024), 2)
                memory_percent = process.memory_percent()

                statsd.gauge('feed.component.process.memory.used', memory_used_mb, tags=[f"component:{name}", f"pid:{pid}"])
                statsd.gauge('feed.component.process.memory.percent', memory_percent, tags=[f"component:{name}", f"pid:{pid}"])

                cpu_percent = process.cpu_percent(interval=1)  # interval of 1 second

                statsd.gauge('feed.component.process.cpu.percent', cpu_percent, tags=[f"component:{name}", f"pid:{pid}"])
            except psutil.NoSuchProcess:
                logger_with_name = logger.bind(comp_name=name)
                logger_with_name.warning(f"Process {pid} no longer exists for component {name}")
                self.latest_pid[id] = None  # Clear the PID since it's no longer valid


    def log_directory_size_sender(self, id, logger_with_name):
        name = self.parser[id]['name']
        runScriptPath = self.parser[id]['runScriptPath']
        if self.parser.has_option(id, 'logDirectory'):
            logDirectory = self.parser[id]['logDirectory']
            if logDirectory == "No":
                return
        else:
            logDirectory = f"{runScriptPath}/logs"
        command = f"du -BM -s {logDirectory}"
        command_output = self.execute_command(command, logger_with_name, f"Log directory size check for {name}")
        
        if command_output:
            output = command_output.stdout.read().strip()
            if output:
                try:
                    size = output.split()[0].rstrip('M')
                    statsd.gauge('feed.component.log_directory.size', size, tags=[f"component:{name}"])
                except IndexError:
                    logger_with_name.error(f"Unexpected output format for log directory size: {output}")
            else:
                logger_with_name.warning(f"No output from 'du' command for {name}")
        else:
            logger_with_name.error(f"Failed to execute log directory size check for {name}")

    def start_component(self, id, logger_with_name):
        name = self.parser[id]['name']
        runScriptPath = self.parser[id]['runScriptPath']
        runScript = self.parser[id]['runScript']
        restart_status = True
        try:
            os.chdir(runScriptPath)

            subprocess.Popen(['sh', runScript], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.PIPE)
            time.sleep(20)
            process_info = self.process_checker(id, logger_with_name)
            process_status = process_info.get('status')
            if process_status == 'running':
                pid = process_info.get('pid')
                self.mail_send(name, "started", restart_status, id)
                statsd.service_check('feed.component.process.status', 0, tags=[f"component:{name}"])
                logger_with_name.info(f"Component {name} restarted successfully (PID:{pid})")
        except FileNotFoundError:
            logger_with_name.error(f"Directory {runScriptPath} not found for component {name}")
        except Exception as e:
            logger_with_name.error(f"Failed to execute ./{runScript} for component {name}. Error: {e}")

    def component_needs_to_run(self, id):
        startTime = self.parser[id]['startTime']
        endTime = self.parser[id]['endTime']
        runninngDates = self.parser[id]['runningDates']
        timeBetween2Days = startTime > endTime
        currenttime = datetime.datetime.now().strftime("%H:%M:%S")
        weekDay = datetime.datetime.now().strftime('%w')
        if (str(weekDay) in str(runninngDates)):
            if timeBetween2Days:
                if not (endTime < currenttime and currenttime < startTime):
                    return True
            else:
                if startTime < currenttime and currenttime < endTime:
                    return True 
        return False   

    def comp_watcher(self, id, stop_event, logger_with_name):
        name = self.parser[id]['name']
        need_to_send_mail = self.parser[id]['needToSendMail'] == 'Yes'
        need_to_up = self.parser[id]['needToUp'] == 'Yes'
        port_check = False
        if self.parser.has_option(id, 'port'):
            port_check = True
        while not stop_event.is_set():
            process_info = self.process_checker(id, logger_with_name)
            process_status = process_info.get('status')
            if self.component_needs_to_run(id):
                if process_status == 'notRunning':
                    pid = self.last_pid.get(id)
                    statsd.service_check('feed.component.process.status', 2, tags=[f"component:{name}"])
                    logger_with_name.info(f"Process status: Not Running")
                    restart_status = need_to_up
                    if need_to_send_mail:
                        self.mail_send(name, "down", restart_status, id)
                    if need_to_up:
                        logger_with_name.warning(f"Component {name} is down. Attempting to restart.")
                        self.start_component(id, logger_with_name)
                    else:
                        logger_with_name.warning(f"Component {name} is configured not to restart.")
                else:
                    pid = process_info.get('pid')
                    statsd.service_check('feed.component.process.status', 0, tags=[f"component:{name}"])
                    logger_with_name.info(f"Process status: Running (PID:{pid})")
                if port_check:
                    self.port_staus_sender(id, logger_with_name)
            else:
                if process_status == 'running':
                    pid = process_info.get('pid')
                    statsd.service_check('feed.component.process.status', 1, tags=[f"component:{name}"])
                    logger_with_name.info(f"Process status: Running.(PID:{pid}) But no need to run")
            if self.process_details_send:
                self.process_details_sender(id)
            if self.logs_size_send:
                self.log_directory_size_sender(id, logger_with_name)
            time.sleep(self.interval)

        if stop_event.is_set():
            logger_with_name.info(f"Watcher thread for component {name} terminated successfully.")

    def watcher_status_sender(self, stop_event):
        while not stop_event.is_set():
            statsd.service_check('feed.component.watcher.status', 0)
            time.sleep(self.interval)


    def start_all_watchers(self):
        for id in self.parser.sections():
            name = self.parser[id]['name']
            logger_with_name = logger.bind(comp_name=name)
            if id in self.threads:
                logger_with_name.warning(f"Watcher thread for component {name} is already running")
                return
            
            logger_with_name.info(f"Starting watcher thread for component {name}")
            stop_event = Event() 
            self.stop_flags[id] = stop_event
            t = Thread(target=self.comp_watcher, args=(id, stop_event, logger_with_name))
            t.start()
            self.threads[id] = t
            logger_with_name.info(f"Watcher thread for component {name} started")
        
        id = 'watcher_thread'
        if id in self.threads:
            logger_with_name.warning(f"Watcher status sender thread is already running")
            return
        logger_with_name = logger.bind(comp_name='WATCHER')
        logger_with_name.info(f"Starting watcher status sender thread")
        stop_event = Event() 
        self.stop_flags[id] = stop_event
        t = Thread(target=self.watcher_status_sender, args=(stop_event,))
        t.start()
        self.threads[id] = t
        logger_with_name.info(f"Watcher status sender thread started")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Component Watcher')
    parser.add_argument('--config', help='Path to the config file', required=True)
    args = parser.parse_args()

    watcher = ComponentWatcher(config_path=args.config)
    watcher.start_all_watchers()
    try:
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        for id in list(watcher.threads):
            logger_with_name = logger.bind(comp_name=watcher.parser[id]['name'])
        logger_with_name = logger.bind(comp_name='')
        logger_with_name.info("Watcher threads stopped.")
    
