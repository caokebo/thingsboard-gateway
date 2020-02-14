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

from thingsboard_gateway.connectors.converter import Converter, log


class CustomOpcdaUplinkConverter(Converter):
    def __init__(self, config):
        self.__config = config
        self.result_dict = {
            'deviceName': config.get('name', 'CustomSerialDevice'),
            'deviceType': config.get('deviceType', 'default'),
            'attributes': [],
            'telemetry': []
        }

    def convert(self, config, data):
        print("data=", data)
        keys = ['attributes', 'telemetry']
        self.result_dict["attributes"] = []
        self.result_dict["telemetry"] = []
        for i, v in enumerate(data):
            (name, val, qual, time) = v
            if qual != "Error":
                path = name.split(".")[1]
                for key in keys:
                    if self.__config.get(key) is not None:
                        for config_object in self.__config.get(key):
                            if config_object["path"] == path:
                                self.result_dict[key].append({config_object['key']: val})
        print("result_dict=", self.result_dict)
        return self.result_dict

