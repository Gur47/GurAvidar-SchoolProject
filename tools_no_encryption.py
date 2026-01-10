########################################################################
# Filename:     tools.py
# Description:  simple "toolbox" of useful functions
#########################################################################

# Imports Section 
import datetime
import os
import hashlib

chunk_size = 1024

# sql injection prevention ready
def get_hash_value(input_string):
    hash_obj = hashlib.sha256()
    hash_obj.update(input_string.encode('utf-8'))
    return hash_obj.hexdigest()


# unique timestams as a string - use it to prevent two files
# from client having the same name
def get_timstamp():
    current_datetime = datetime.datetime.now()
    result = current_datetime.timestamp()
    return str(result)

       
# get binaary file from socket and save to path
def get_binary_file_and_save_to_path(mysocket, file_path):

    size = int(mysocket.recv(chunk_size).decode())
    
    # open and write picture
    with open(file_path, mode='wb') as file: # b is important -> binary
        total = 0
        # get "chunks"
        while total + chunk_size < size:
            chunk = mysocket.recv(1024)
            file.write(chunk)
            total = total + chunk_size
        # get "tail"
        if (total < size):
            data = mysocket.recv(size - total) 
            file.write(data)


def get_size_of_file(file_path) :
    file_stats = os.stat(file_path)
    return file_stats.st_size        


# send binary file 
def send_binary_file(mysocket, file_path):
    # send size of the file
    size = get_size_of_file(file_path)
    mysocket.send(str(size).encode())
    
    # open and read binary file
    with open(file_path, mode='rb') as file: # b is important -> binary
        total = 0
        # send "chunks"b
        while total + chunk_size < size:
            chunk = file.read(chunk_size)
            mysocket.send(chunk)
            total = total + chunk_size
        # send "tail"
        if (total < size):
            data = file.read(size - total)
            mysocket.send(data)
