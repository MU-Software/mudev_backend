import math
import types
import json


def frame_name(o): return f"<class: {getattr(o, '__framename__', o.__name__)}>"
def frame_str(x): return json.dumps(x, default=frame_name, indent=4)
def frame_print(x): return print('\nResult : ' + frame_str(getattr(x, 'to_dict', (lambda: None))()))


def split_nth_char(x, n=2): return [x[i:i+n] for i in range(0, len(x), n)]
def bin_len(x): return len(bin(int(x, 16))[2:])
def ceil_pow2(x): return pow(2, math.ceil(math.log(x)/math.log(2)))
def ceil_mul8(x): return 8 * math.ceil(x / 8)
def hex_2_bin(x): return bin(int(x, 16))[2:].zfill(ceil_mul8(bin_len(x)))


def hex_to_mac_addr(target):
    target = target.strip().zfill(12)
    result_str = f'{target[ 0: 2]}:{target[ 2: 4]}:'
    result_str += f'{target[ 4: 6]}:{target[ 6: 8]}:'
    result_str += f'{target[ 8:10]}:{target[10:  ]}'
    return result_str


def hex_to_ipv4_addr(target):
    result_str = ''
    for byte in split_nth_char(target.strip().zfill(8)):
        result_str += f'{int(byte, 16)}.'
    return result_str[:-1]


def hex_to_ipv6_addr(target):
    target = split_nth_char(target.strip().zfill(32), 4)
    target = list(map(lambda x: int(x, 16), target))
    result_str = ''
    for byte in target:
        if byte:
            result_str += hex(byte)[2:]
        result_str += ':'
    return result_str


class Frame:  # DONE
    __framename__ = 'frame'
    __OSI_layer__ = 0

    frame_raw = None
    frame_bin = None

    data_type = None
    data = None
    data_raw: str = None

    def __len__(self):
        if hasattr(self, 'size'):
            return int(getattr(self, 'size', 0))
        else:
            # We should divide the size of the raw frame data to 2,
            # because two characters are one byte. (0xff == 1byte)
            return int(len(self.frame_raw) / 2)

    def to_dict(self, include_frame_data=False):
        result_dict = dict()

        for k, v in vars(self).items():
            if not isinstance(v, (types.FunctionType, types.MethodType)):
                if not k.startswith('_'):
                    if isinstance(v, Frame) and getattr(v, 'to_dict', False):
                        result_dict[k] = v.to_dict(include_frame_data)
                    else:
                        if 'frame' in k:
                            continue
                        if not include_frame_data and k == 'data_raw':
                            continue
                        result_dict[k] = v

        return result_dict


class Ethernet(Frame):  # DONE
    __framename__ = 'Ethernet II'
    __OSI_layer__ = 2

    dest_mac_addr: str = ''
    src_mac_addr: str = ''

    def __init__(self, frame_data):
        self.frame_raw = frame_data
        self.frame_bin = hex_2_bin(frame_data)

        self.dest_mac_addr = hex_to_mac_addr(self.frame_raw[0:12])
        self.src_mac_addr = hex_to_mac_addr(self.frame_raw[12:24])

        self.dest_mac_addr += ' Unicast' if self.dest_mac_addr.startswith('00') else ''
        self.src_mac_addr += ' Unicast' if self.src_mac_addr.startswith('00') else ''

        self.data_type = EtherType.get(int(self.frame_raw[24:28], 16), None)
        self.data_raw = self.frame_raw[28:]
        self.data = self.data_type(self.data_raw) if self.data_type else None


ARP_HwDesc = {
    1: 'Ethernet',
    14: 'SMDS',
    15: 'F/R',
    17: 'HLDC', }
ARP_ProtocolDesc = {
    0x0800: 'IP',
    0x0805: 'X.25', }


class ARP(Frame):  # DONE
    __framename__ = 'ARP'
    __OSI_layer__ = 3

    hw_type: int = 0
    hw_size: int = 0
    hw_desc: str = ''
    protocol_type: int = 0
    protocol_size: int = 0
    protocol_desc: str = ''
    operation = 1  # Request: 1, Reply: 2
    operation_desc: str = ''

    src_mac_addr: str = ''
    src_ip_addr: str = ''
    dest_mac_addr: str = ''
    dest_ip_addr: str = ''

    def __init__(self, frame_data):
        self.frame_raw = frame_data
        self.frame_bin = hex_2_bin(frame_data)

        self.hw_type = int(self.frame_raw[:4], 16)
        self.hw_size = int(self.frame_raw[8:10], 16) * 8
        self.hw_desc = ARP_HwDesc.get(self.hw_type, 'Unknown HW')

        self.protocol_type = int(self.frame_raw[4:8], 16)
        self.protocol_size = int(self.frame_raw[10:12], 16) * 8
        self.protocol_desc = ARP_ProtocolDesc.get(self.protocol_type, 'Unknown Protocol')

        if self.protocol_desc != 'IP':
            raise NotImplementedError(f'Protocol {self.protocol_desc} not implemented yet.')

        self.operation = int(self.frame_raw[12:16], 16)
        self.operation_desc = 'Request(Destination MAC empty)' if self.operation == 1 else 'Reply'

        self.src_mac_addr = hex_to_mac_addr(self.frame_raw[16:28])
        self.src_ip_addr = hex_to_ipv4_addr(self.frame_raw[28:36])

        self.dest_mac_addr = hex_to_mac_addr(self.frame_raw[36:48])
        self.dest_ip_addr = hex_to_ipv4_addr(self.frame_raw[48:56])


service_type_list = {
    0: 'Normal',
    1: 'Minimize Cost',
    2: 'Maximize Reliablilty',
    4: 'Maximize Throughput',
    8: 'Minimize Delay',
    15: 'Maximize Security', }


class IPv4(Frame):  # DONE
    __framename__ = 'IPv4'
    __OSI_layer__ = 3

    version: int = 0
    header_size: int = 0
    service_type = None
    service_type_desc: str = ''
    size: int = 0
    id = None

    do_not_fragment: bool = False
    more_fragment: bool = False

    fragment_offset: int = 0
    ttl = None
    protocol = None
    header_checksum = None

    src_ip_addr: str = ''
    dest_ip_addr: str = ''

    options = None

    def __init__(self, frame_data):
        self.frame_raw = frame_data
        self.frame_bin = hex_2_bin(frame_data)

        self.version = int(self.frame_raw[:1], 16)
        assert self.version == 4, 'IPv4 version mismatch!'

        # IPv4 packets are displayed in 4byte increments.
        self.header_size = int(self.frame_raw[1:2], 16) * 4

        self.service_type = int(self.frame_raw[2:4], 16)
        self.service_type_desc = service_type_list.get(self.service_type, '')

        self.size = int(self.frame_raw[4:8], 16)
        self.id = int(self.frame_raw[8:12], 16)

        flags = int(self.frame_raw[12:13], 16) >> 1
        self.do_not_fragment = (flags & 0b10) != 0
        self.more_fragment = (flags & 0b01) != 0

        self.fragment_offset = int(self.frame_raw[12:16], 16) & 0x1FFF

        # Time to live
        self.ttl = int(self.frame_raw[16:18], 16)
        self.protocol = int(self.frame_raw[18:20], 16)
        self.header_checksum = self.frame_raw[20:24]

        self.src_ip_addr = hex_to_ipv4_addr(self.frame_raw[24:32])
        self.dest_ip_addr = hex_to_ipv4_addr(self.frame_raw[32:40])

        header_end_pos = self.header_size * 2
        self.options = self.frame_raw[40:header_end_pos]

        self.data_raw = self.frame_raw[header_end_pos:]
        self.data_type = IPProtocolNum.get(self.protocol, None)
        self.data = self.data_type(self.data_raw) if self.data_type else None


class IPv6(Frame):
    __framename__ = 'IPv6'
    __OSI_layer__ = 3

    version: int = 0
    traffic_class = None
    flow_label = None
    payload_size: int = 0
    next_header = None
    hop_limit = None

    src_addr: str = ''
    dest_addr: str = ''

    payload: str = ''

    def __init__(self, frame_data):
        self.frame_raw = frame_data
        self.frame_bin = hex_2_bin(frame_data)

        self.version = int(self.frame_raw[:1], 16)
        assert self.version == 6, 'IPv6 version mismatch!'

        # Traffic class is similar as Service Type on IPv4
        self.traffic_class = int(self.frame_raw[1:3], 16)

        self.flow_label = int(self.frame_raw[3:8], 16)
        self.payload_size = int(self.frame_raw[8:12], 16)
        self.next_header = int(self.frame_raw[12:14], 16)
        self.hop_limit = int(self.frame_raw[14:16], 16)

        self.src_addr = self.frame_raw[16:48]
        self.dest_addr = self.frame_raw[48:80]

        self.data = self.payload = self.frame_raw[80:]


ICMP_msg = {
    0: ('Echo Reply', {}),
    3: ('Destination Unreachable', {
        0: 'Network Unreachable',
        1: 'Host Unreachable',
        2: 'Protocol Unreachable',
        6: 'Destination Network Unreachable',
        7: 'Destination Host Unreachable',
    }),
    5: ('Redirect', {
        0: 'Redirect Datagram for the Network',
        1: 'Redirect Datagram for the Host',
    }),
    8: ('Echo Request', {}),
    11: ('Time Exceeded', {
        0: 'Time to Live exceeded in Transit',
        1: 'Fragment Reassembly Time Exceeded',
    }), }


class ICMP(Frame):
    __framename__ = 'ICMP'
    __OSI_layer__ = 3

    icmp_type: int = 0
    icmp_code: int = 0
    icmp_desc: str = ''

    checksum: str = None

    id: int = 0
    seq_num: int = 0

    def __init__(self, frame_data):
        self.frame_raw = frame_data
        self.frame_bin = hex_2_bin(frame_data)

        self.icmp_type = int(self.frame_raw[:2], 16)
        self.icmp_code = int(self.frame_raw[2:4], 16)
        icmp_type_code = ICMP_msg.get(self.icmp_type, ('Unknown', {}))
        self.icmp_desc = icmp_type_code[0]
        if icmp_type_code[1]:
            self.icmp_desc += f'{icmp_type_code[1].get(self.icmp_desc, "Unknown")}'

        self.checksum = self.frame_raw[4:8]

        self.id = int(self.frame_raw[8:12], 16)
        self.seq_num = int(self.frame_raw[12:16], 16)

        self.data_raw = self.frame_raw[16:]


class TCP(Frame):
    __framename__ = 'TCP'
    __OSI_layer__ = 4

    src_port: int = 0
    dest_port: int = 0
    sequence_num: int = 0
    acknowledgement_num: int = 0
    header_size: int = 0

    URG = False
    ACK = False
    PSH = False
    RST = False
    SYN = False
    FIN = False

    window_size = 0
    checksum = None
    urgent_pointer = 0
    option = None

    service_expect: str = ''

    def __init__(self, frame_data):
        self.frame_raw = frame_data
        self.frame_bin = hex_2_bin(frame_data)

        self.src_port = int(self.frame_raw[:4], 16)
        self.dest_port = int(self.frame_raw[4:8], 16)

        self.service_expect = WellKnownPort.get(
            self.src_port,
            WellKnownPort.get(
                self.dest_port,
                'Unknown'))
        self.direction_expect = 'Unknown' if self.service_expect == 'Unknown'\
            else 'Response' if WellKnownPort.get(self.src_port, False)\
            else 'Request' if WellKnownPort.get(self.dest_port, False)\
            else 'Unknown'

        # The sequence number of TCP segment.
        # TCP packet can be splited into segments.
        self.sequence_num = int(self.frame_raw[8:16], 16)
        # This field is used to determine the next packet sequence number.
        self.acknowledgement_num = int(self.frame_raw[16:24], 16)

        # TCP packets are displayed in 4byte increments.
        self.header_size = int(self.frame_raw[24:25], 16) * 4
        # int(self.frame_raw[25:26], 16) is reserved

        bit_collection = int(self.frame_raw[26:28], 16)
        # Urgent Bit
        self.URG = (bit_collection & 0b00100000) != 0
        # Acknowledgement Bit, I successfully received previous data!
        self.ACK = (bit_collection & 0b00010000) != 0
        # Push Bit
        self.PSH = (bit_collection & 0b00001000) != 0
        # Reset Bit, Please reset this TCP Connection.
        self.RST = (bit_collection & 0b00000100) != 0
        # Sync Bit, We are 3-way handshaking now.
        self.SYN = (bit_collection & 0b00000010) != 0
        # Finish Bit, I want to quit this session.
        self.FIN = (bit_collection & 0b00000001) != 0

        # Possible size of maximum receivable TCP buffer
        self.window_size = int(self.frame_raw[28:32], 16)

        self.checksum = self.frame_raw[32:36]
        # Urgent pointer works only when URG bit set.
        # This field is used to tell which segment should be treated as urgent data.
        self.urgent_pointer = int(self.frame_raw[36:40], 16)

        self.option = self.frame_raw[40:self.header_size*2]
        self.data_raw = self.frame_raw[self.header_size*2:]


class UDP(Frame):
    __framename__ = 'UDP'
    __OSI_layer__ = 4

    src_port: int = 0
    dest_port: int = 0
    size: int = 0
    checksum = None

    def __init__(self, frame_data):
        self.frame_raw = frame_data
        self.frame_bin = hex_2_bin(frame_data)

        self.src_port = int(self.frame_raw[:4], 16)
        self.dest_port = int(self.frame_raw[4:8], 16)
        self.size = int(self.frame_raw[8:12], 16)
        self.checksum = int(self.frame_raw[8:12], 16)

        self.data_raw = self.frame_raw[12:]

    def calculate_checksum(self):
        # TODO : Implement this
        raise NotImplementedError()

    def validate_checksum(self):
        if self.checksum == 0:
            print('Checksum validation disabled on frame data!')
            return True

        # TODO : Implement this
        raise NotImplementedError()


EtherType = {
    0x0800: IPv4,
    0x86DD: IPv6,
    0x0806: ARP,
}

IPProtocolNum = {
    1: ICMP,
    6: TCP,
    17: UDP,
}

WellKnownPort = {
    20: 'FTP(data)',
    21: 'FTP(control)',
    22: 'SSH',
    23: 'TELNET',
    25: 'SMTP',
    26: 'RSFTP',
    43: 'WHOIS',
    53: 'DNS',
    57: 'MTP(Mail Transfer Protocol)',
    80: 'HTTP',
    115: 'SFTP',
    118: 'SQL Service',
    123: 'NTP',
    143: 'IMAP4',
    156: 'SQL Service',
    194: 'IRC',
    220: 'IMAP v3',
    389: 'LDAP',
    443: 'HTTPS',
    465: 'SMTP over SSL',
    546: 'DHCPv6 client',
    547: 'DHCPv6 server',
    873: 'rsync',
    989: 'FTPS(data)',
    990: 'FTPS(control)',
    992: 'TELNET over SSL',
    993: 'IMAP over SSL',
    995: 'POP3 over SSL',
}

if __name__ == '__main__':
    while True:
        input_data = input('패킷 데이터를 입력해주세요:\n')
        if not input_data:
            continue
        try:
            frame_print(Ethernet(input_data))
            break
        except Exception as err:
            print('올바른 패킷 데이터가 아닙니다.\n')
            print(err)
            continue
