# RDTP (Reliable Data Transfer Protocol)

## Dpendencies
To install the dependencies, run the following commands:
```bash
python -m venv venv
venv/bin/activate
pip install -r dev_requirements.txt -r requirements.txt
pre-commit install
```

## Tests
Once you have installed the dependencies, run the tests with the following command:
```bash
pytest
```

## Usage

### Running the server

To run the server, use the following command:
```bash
python src/server [-h] [-v | -q] [-H ADDR] [-p PORT] [-s DIRPATH]
```
Optional arguments:
- `-h`, `--help`: Show this help message and exit
- `-v`, `--verbose`: Increase output verbosity
- `-q`, `--quiet`: Decrease output verbosity
- `-H ADDR`, `--host ADDR`: Server IP address
- `-p PORT`, `--port PORT`: Server port
- `-s DIRPATH`, `--storage DIRPATH`: Destination file path

### Running the client

The client functionality is divided into two commands: `upload` and `download`.

#### Uploading a file

To upload a file, use the following command:
```bash
python src/upload [-h] [-v | -q] [-H ADDR] [-p PORT] [-s FILEPATH] [-n FILENAME]
```
Optional arguments:
- `-h`, `--help`: Show this help message and exit
- `-v`, `--verbose`: Increase output verbosity
- `-q`, `--quiet`: Decrease output verbosity
- `-H ADDR`, `--host ADDR`: Server IP address
- `-p PORT`, `--port PORT`: Server port
- `-s FILEPATH`, `--src FILEPATH`: Source file path
- `-n FILENAME`, `--name FILENAME`: File name

#### Downloading a file

To download a file, use the following command:
```bash
python src/download [-h] [-v | -q] [-H ADDR] [-p PORT] [-d FILEPATH] [-n FILENAME]
```
Optional arguments:
- `-h`, `--help`: Show this help message and exit
- `-v`, `--verbose`: Increase output verbosity
- `-q`, `--quiet`: Decrease output verbosity
- `-H ADDR`, `--host ADDR`: Server IP address
- `-p PORT`, `--port PORT`: Server port
- `-d FILEPATH`, `--dst FILEPATH`: Destination file path
- `-n FILENAME`, `--name FILENAME`: File name
