import logging
import sys
from pathlib import Path
from typing import Union
from .transport import sockaddr, RDTTransport, RDTSegment, StopAndWaitTransport, SelectiveAckTransport

UPLOAD_CHUNK_SIZE = 4096
DOWNLOAD_CHUNK_SIZE = 4096


class DownloadOperation:
    opcode = b"d"

    def __init__(
        self,
        transport: RDTTransport,
        filename: str,
        destination: Union[str, Path] = None,
    ) -> None:
        self.transport = transport
        self.filename = filename
        self.destination = Path(destination) if destination else filename

    def get_op_metadata(self) -> bytes:
        data = self.opcode  # operation code (1 byte)
        data += len(self.filename).to_bytes(
            length=1, byteorder=sys.byteorder
        )  # filename size (1 byte)
        data += self.filename.encode()  # filename (up to 255 bytes)
        return data

    @staticmethod
    def unpack(transport: RDTTransport, data: bytes):
        filename_size = int.from_bytes(data[:1], byteorder=sys.byteorder)
        filename = data[1 : 1 + filename_size].decode()
        return DownloadOperation(transport, filename)

    def handle(self, addr: sockaddr):
        logging.info(f"Starting download for file {self.filename}")
        # tell the server what we're going to do
        self.transport.send(self.get_op_metadata(), addr)
        resp, _ = self.transport.receive(4)
        file_size = int.from_bytes(resp.data, sys.byteorder)
        logging.debug(f"Got file size of {file_size}, fetching data")
        bytes_written = 0
        with open(self.destination, "wb") as f:
            if (isinstance(self.transport, StopAndWaitTransport)):
                while bytes_written < file_size:
                    pkt, _ = self.transport.receive(DOWNLOAD_CHUNK_SIZE)
                    bytes_written += f.write(pkt.data)
            else: 
                while bytes_written < file_size:
                    pkt, _ = self.transport.receive(DOWNLOAD_CHUNK_SIZE)
                    bytes_written += f.write(pkt.data)


class UploadOperation:
    opcode = b"u"

    def __init__(
        self,
        transport: RDTTransport,
        filepath: Union[str, Path],
        destination: Union[str, Path],
        file_size: int = None,
    ) -> None:
        self.transport = transport
        self.filepath = Path(filepath)
        self.file_size = file_size or self.filepath.stat().st_size
        self.destination = Path(destination)

    @staticmethod
    def unpack(transport: RDTTransport, data: bytes):
        file_size = int.from_bytes(data[:4], byteorder=sys.byteorder)
        filename_size = int.from_bytes(data[4:5], byteorder=sys.byteorder)
        filename = data[5 : 5 + filename_size].decode()
        data = data[5 + filename_size :]
        dest_size = int.from_bytes(data[:2], byteorder=sys.byteorder)
        dest = data[2 : 2 + dest_size].decode()
        return UploadOperation(transport, filename, dest, file_size)

    def get_op_metadata(self) -> bytes:
        filename = self.filepath.name
        dest = str(self.destination)
        data = self.opcode  # operation code (1 byte)
        data += self.file_size.to_bytes(
            length=4, byteorder=sys.byteorder
        )  # file size (4 bytes)
        data += len(filename).to_bytes(
            length=1, byteorder=sys.byteorder
        )  # filename size (1 byte)
        data += filename.encode()  # filename (up to 255 bytes)
        data += len(dest).to_bytes(
            length=2, byteorder=sys.byteorder
        )  # dest path size (2 bytes)
        data += dest.encode()  # dest path (up to 65535 bytes)
        return data

    def handle(self, addr: sockaddr):
        # tell the server what we're going to do
        
        self.transport.send(self.get_op_metadata(), addr)
        while self.transport.get_window_size():
            self.transport.update_window()
        print("Se envio:D")
        # upload the file in chunks of size UPLOAD_CHUNK_SIZE if
        # it's less than the file size
        bytes_read = 0
        full_window = False
        content_read = 0
        chunk_size = min(UPLOAD_CHUNK_SIZE, self.file_size)
        with open(self.filepath, "rb") as file:
            while bytes_read < self.file_size:
                if (not self.transport.has_full_window() and content_read < self.file_size):
                    content = file.read(chunk_size)
                    content_read += len(content)
                    bytes_read += self.transport.send(content, addr)
                else:
                    bytes_read += self.transport.update_window()
                full_window = bytes_read == 0
                # print(f"se enviaron: {bytes_read} con content: {content}")


operations = {
    UploadOperation.opcode: UploadOperation,
    DownloadOperation.opcode: DownloadOperation,
}


def unpack_operation(transport: RDTTransport, data: bytes):
    opcode = data[:1]
    if opcode not in operations:
        raise ValueError("Invalid operation")
    return operations[opcode].unpack(transport, data[1:])


def run_operation(opcode: bytes, src: str, host: str, port: int, dest: str):
    addr = sockaddr(host, port)
    with SelectiveAckTransport() as transport:
        # create the operation and run it
        op = operations[opcode](transport, src, dest)
        return op.handle(addr)
