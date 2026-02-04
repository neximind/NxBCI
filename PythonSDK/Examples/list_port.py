from serial.tools import list_ports

ports_list = list(list_ports.comports())
print("可用串口列表:")
for p in ports_list:
    print(f"{p.device} - {p.description}")