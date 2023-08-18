#!/usr/bin/python3.9
import datetime
import configparser
from send_mail import mail_send 
import time
import subprocess
import logging
import os
from threading import Thread
import subprocess
import socket
import psutil
import datetime
from websocketclient import send_component_data

parser = configparser.ConfigParser()
logging.basicConfig(filename='./logs/watcher.log', format='%(asctime)s %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

parser.read('./config/config.ini') 

prev_process_state_dict = {}
prev_port_state_dict = {}
hostname = socket.gethostname()
ip = socket.gethostbyname(hostname)

def processChecker(tag):
   process = subprocess.Popen("ps x|grep -ai {} |grep -v grep |wc -l".format(tag),
                           shell=True, stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                           universal_newlines=True)
   output=int(process.stdout.read())
   if output > 0:
    return 'running'
   else:
    return 'notRunning'
def portChecker(port):
   if port == 'No':
      return 'noPort'
   else:
      process = subprocess.Popen("netstat -tulpn | grep {} | wc -l".format(port),
                              shell=True, stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                              universal_newlines=True)
      output=int(process.stdout.read())
      if output > 0:
         return 'open'
      else:
         return 'notOpen'

def upTimeGenerator(tag):
   process_id_string = subprocess.Popen("ps x|grep -ai {} |grep -v grep ".format(tag),
                           shell=True, stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                           universal_newlines=True)
   
   output=str(process_id_string.stdout.read())
   output_list = output.split(" ")
   new_list = list(filter(None, output_list))
   print(f"{tag} {new_list}")

   if not (len(new_list) == 0):
      pid_string = new_list[0]
      print(f"{tag} {pid_string}")
      pid = int(pid_string)
      print(pid)
      process = psutil.Process(pid)
      start_time = process.create_time()
      start_time_formatted = datetime.datetime.fromtimestamp(start_time).strftime("%Y-%m-%dT%H:%M:%SZ")
      return start_time_formatted
   else:
      return '----------------'

   

def isSendData(parser, id, process_status, port_status):
   name = parser[id]['name']
   tag = parser[id]['tag']
   category = parser[id]['category']
   port = parser[id]['port']
   startTime = parser[id]['startTime']
   endTime = parser[id]['endTime']
   runninngDates = parser[id]['runninngDates']
   
   if (prev_process_state_dict[id] !=  process_status) or (prev_port_state_dict[id] !=  port_status):
      prev_process_state_dict[id] = process_status
      prev_port_state_dict[id] = port_status
      uptime = upTimeGenerator(tag)
      print(f"sending data from {name}")
      t = Thread(target=send_component_data, args=(ip, id, category, name, process_status, port, port_status,startTime,endTime,runninngDates,uptime,))
      t.start()

def tasksToDo(parser, id):
   name = parser[id]['name']
   tag = parser[id]['tag']
   port = parser[id]['port']
   needToSendMail = parser[id]['needToSendMail']
   needToUp = parser[id]['needToUp']
   process_status = processChecker(tag)
   port_status = portChecker(port)
   isSendData(parser, id, process_status, port_status)
   if process_status == 'notRunning':
      if needToSendMail == 'Yes':
         try:
            mail_send(name)
         except Exception as e:
            logger.error(f":{name} : {e}")
      if needToUp == 'Yes':
         logger.debug( f":{name} : Not running. Restarting the component")
         try:
            runScriptPath = parser[id]['runScriptPath']
            runScript = parser[id]['runScript']
         except:
            logger.error( f":{name} : runScriptPath and runScript is not defined")
         try:
            os.chdir(runScriptPath)
         except:
            logger.error( f":{name} : {runScriptPath} directory not found")
         try:
            # output = subprocess.check_output(['sh', runScript, '&'])
            process = subprocess.Popen(['sh', runScript], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.PIPE)
            logger.debug( f":{name} Successfully Restarted")
            time.sleep(10)
         except:
            logger.error( f":{name} : ./{runScript} cannot execute")
      else:
         logger.debug( f":{name} : Not running. Configured not to up")

for id in parser.sections():
   prev_process_state_dict[id] = 'processing'
   prev_port_state_dict[id] = 'processing'

def component_item(id):
   startTime = parser[id]['startTime']
   endTime = parser[id]['endTime']
   runninngDates = parser[id]['runninngDates']
   if (startTime > endTime):
      timeBetween2Days = True
   else:
      timeBetween2Days = False
   while True:   
      currenttime = datetime.datetime.now().strftime("%H:%M:%S")
      weekDay = datetime.datetime.now().strftime('%w')

      if (str(weekDay) in str(runninngDates)):
         if timeBetween2Days:
            if not (endTime < currenttime and currenttime < startTime):
               tasksToDo(parser, id)
            else:
               isSendData(parser, id, 'notStarted', 'notStarted')
         else:
            if startTime < currenttime and currenttime < endTime:
               tasksToDo(parser, id)
            else:
               isSendData(parser, id, 'notStarted', 'notStarted') 
      else:
         isSendData(parser, id, 'notStarted', 'notStarted')
      # print(f"here {id}")        
      time.sleep(5)

for id in parser.sections():
   t = Thread(target=component_item, args=(id, ))
   t.start()
   time.sleep(1)