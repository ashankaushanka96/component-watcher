#!/usr/bin/env python

import asyncio
import websockets
import sys
import json
#ip, id, category, name, process_status, port, port_status,startTime,endTime,runninngDates
def json_data(ip, id, category, name, process_status, port, port_status,startTime,endTime,runninngDates,uptime):
    # data_set_array = []
    obj = {'ip': ip, 'id': id, 'category': category, 'name': name, 'process_status':process_status, 'port':port, 'port_status':port_status,'startTime':startTime,'endTime':endTime,'runninngDates':runninngDates, 'uptime':uptime}
    print(obj)
    # data_set_array.append(obj)
    data_set = obj
    json_dump = json.dumps(data_set)

    return json_dump

async def send_data(ip, id, category, name, process_status, port, port_status,startTime,endTime,runninngDates,uptime):
    async with websockets.connect("ws://172.20.162.55:8765") as websocket:
        await websocket.send(json_data(ip, id, category, name, process_status, port, port_status,startTime,endTime,runninngDates,uptime))


def main(ip, id, category, name, process_status, port, port_status,startTime,endTime,runninngDates,uptime):
    try:
        asyncio.run(send_data(ip, id, category, name, process_status, port, port_status,startTime,endTime,runninngDates,uptime))
        return True
    except Exception as e:
        return False
def send_component_data(ip, id, category, name, process_status, port, port_status,startTime,endTime,runninngDates,uptime):    
    while True:
        if main(ip, id, category, name, process_status, port, port_status,startTime,endTime,runninngDates,uptime):
            break
        elif  not main(ip, id, category, name, process_status, port, port_status,startTime,endTime,runninngDates,uptime):
            main(ip, id, category, name, process_status, port, port_status,startTime,endTime,runninngDates,uptime)