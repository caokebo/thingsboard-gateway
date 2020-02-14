#     Copyright 2020. ThingsBoard
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.

"""Import libraries"""

import serial
import time
import traceback
import Pyro4
from threading import Thread
from random import choice
from string import ascii_lowercase
from thingsboard_gateway.connectors.connector import Connector, log    # Import base class for connector and logger
from thingsboard_gateway.tb_utility.tb_utility import TBUtility
import thingsboard_gateway.extensions.opcda.OpenOPC as OpenOPC
from thingsboard_gateway.extensions.opcda.opcda_converter import CustomOpcdaUplinkConverter


class CustomOpcdaConnector(Thread, Connector):    # Define a connector class, it should inherit from "Connector" class.
    def __init__(self, gateway,  config, connector_type):
        super().__init__()    # Initialize parents classes
        self.statistics = {'MessagesReceived': 0,
                           'MessagesSent': 0}    # Dictionary, will save information about count received and sent messages.
        self.__config = config    # Save configuration from the configuration file.
        self.__gateway = gateway    # Save gateway object, we will use some gateway methods for adding devices and saving data from them.
        self.__connector_type = connector_type    # Saving type for connector, need for loading converter
        self.setName(self.__config.get("name",
                                       "Custom %s connector " % self.get_name() + ''.join(choice(ascii_lowercase) for _ in range(5))))    # get from the configuration or create name for logs.
        log.info("Starting Custom %s connector", self.get_name())    # Send message to logger
        self.daemon = True    # Set self thread as daemon
        self.stopped = True    # Service variable for check state
        self.connected = False    # Service variable for check connection to device
        self.devices = {}    # Dictionary with devices, will contain devices configurations, converters for devices and serial port objects
        self.load_converters()    # Call function to load converters and save it into devices dictionary
        self.opc_servers = {}
        self.__connect_to_devices()    # Call function for connect to devices
        log.info('Custom connector %s initialization success.', self.get_name())    # Message to logger
        log.info("Devices in configuration file found: %s ", '\n'.join(device for device in self.devices))    # Message to logger

    def __connect_to_devices(self):    # Function for opening connection and connecting to devices
        print("__connect_to_devices=", self.devices)
        try:
            for opc_server in self.__config["opcServerList"]:
                opc = OpenOPC.open_client(host=opc_server["opcProxyIp"], port=opc_server["opcProxyPort"])
                opc.connect(opc_server["opcServer"])
                self.opc_servers[opc_server["serverId"]] = {"opc": opc, "collectInterval": opc_server["collectInterval"]}
        except OpenOPC.OPCError:
            print("OpenOPC.OPCError")
            traceback.print_exc()
        except Pyro4.errors.CommunicationError:
            # [WinError 10060] 由于连接方在一段时间后没有正确答复或连接的主机没有反应，连接尝试失败。 地址错误
            # [WinError 10061] 由于目标计算机积极拒绝，无法连接。 端口错误
            print("Pyro4.errors.CommunicationError")
            traceback.print_exc()
        else:    # if no exception handled - add device and change connection state
            self.connected = True

    def open(self):    # Function called by gateway on start
        self.stopped = False
        self.start()

    def get_name(self):    # Function used for logging, sending data and statistic
        return self.name

    def is_connected(self):    # Function for checking connection state
        return self.connected

    def load_converters(self):    # Function for search a converter and save it.
        devices_config = self.__config.get('devices')
        try:
            if devices_config:
                for device_config in devices_config:
                    if device_config.get('converter') is not None:
                        converter = TBUtility.check_and_import(self.__connector_type, device_config['converter'])
                        self.devices[device_config['name']] = {'converter': converter(device_config),
                                                               'device_config': device_config}
                    else:
                        converter = CustomOpcdaUplinkConverter(device_config)
                        self.devices[device_config['name']] = {'converter': converter, 'device_config': device_config}
            else:
                log.error('Section "devices" in the configuration not found. A custom connector %s has being stopped.', self.get_name())
                self.close()
        except Exception as e:
            log.exception(e)

    def run(self):    # Main loop of thread
        try:
            while True:
                for server_id in self.opc_servers:
                    tag_list = []
                    for device in self.devices:
                        if server_id == self.devices[device]["device_config"]["serverId"]:
                            for attribute in self.devices[device]["device_config"]["attributes"]:
                                tag_list.append(device+"."+attribute["path"])
                            for timeserie in self.devices[device]["device_config"]["telemetry"]:
                                tag_list.append(device+"."+timeserie["path"])
                    data_from_device = self.opc_servers[server_id]["opc"].read(tag_list)
                    converted_data = self.devices[device]['converter'].convert(self.devices[device]['device_config'], data_from_device)
                    self.__gateway.send_to_storage(self.get_name(), converted_data)
                time.sleep(5)
                if not self.connected:
                    break
        except Exception as e:
            log.exception(e)
            self.close()

    def close(self):    # Close connect function, usually used if exception handled in gateway main loop or in connector main loop
        self.stopped = True
        for opc_server in self.opc_servers:
            try:
                if self.devices[opc_server]['opc'].ping():
                    self.devices[opc_server]['opc'].close()
            except Pyro4.errors.DaemonError:
                traceback.print_exc()


    def on_attributes_update(self, content):    # Function used for processing attribute update requests from ThingsBoard
        log.debug(content)
        # if self.devices.get(content["device"]) is not None:
        #     device_config = self.devices[content["device"]].get("device_config")
        #     if device_config is not None:
        #         log.debug(device_config)
        #         if device_config.get("attributeUpdates") is not None:
        #             requests = device_config["attributeUpdates"]
        #             for request in requests:
        #                 attribute = request.get("attributeOnThingsBoard")
        #                 log.debug(attribute)
        #                 if attribute is not None and attribute in content["data"]:
        #                     try:
        #                         value = content["data"][attribute]
        #                         str_to_send = str(request["stringToDevice"].replace("${" + attribute + "}", str(value))).encode("UTF-8")
        #                         self.devices[content["device"]]["serial"].write(str_to_send)
        #                         log.debug("Attribute update request to device %s : %s", content["device"], str_to_send)
        #                         time.sleep(.01)
        #                     except Exception as e:
        #                         log.exception(e)
        # try:
        #     # 写入方式一
        #     # opc.write(('Bucket Brigade.Int4', 100.0))
        #     # 写入方式二
        #     opc.write([('Bucket Brigade.Int4', 10.0), ('Bucket Brigade.Int2', 20.0)])
        #     print(opc.servers())
        #     print(opc.list())
        #     print(opc.list('Simulation Items'))
        #     print(opc.list('Configured Aliases'))
        #     print(opc.list('Simulation Items.Random.*Real*'))
        #     print(opc.info())
        #     # while True:
        #     #     v = opc.read(taglist)
        #     #     for i in range(len(v)):
        #     #         (name, val, qual, time) = v[i]
        #     #         print('% -15s % -15s % -15s % -15s'% (name, val, qual, time))
        # except Exception as e:
        #     print(e)
        # finally:
        #     opc.close()

    def server_side_rpc_handler(self, content):
        pass
