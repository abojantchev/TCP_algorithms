from socket import *
from sys import getsizeof
import select
from math import log
from time import time


def main():

    delays = []  # store pocket delay
    throughputs = []  # store size of packet
    filePath = "message.txt"

    serverName = gethostbyname(gethostname())  # local server
    pocketSize = 1000  # size of a pocket sent to server
    pocketNumber = 1  # tracking number of pockets sent to server
    
    window = []  # container of multiple packets send to receiver at a time
    waitingACK = [] # sequence number of packets in the window
    delayACK = []  # delays of packets in the window
    previousResponse = []
    receivedTime = []  # Time list that saves the packet arriving time
    receivedACK = []
    send_base = 0  #acknowledgment as interger
    base_index = 0
    responseQueue = 0  # number of packets in transaction
    noData = False # true if readfile is empty
    timeReset = [-1,0]
    
    # Vegas setting
    fixedSize = 1  # window size
    # ssthresh = 16
    cwndWindow = []
    base_rtt = 0
    rtt = 0

    # user input port
    serverPort = int(input("Enter the Port number you want your receiver to run: "))

    # setup a socket with timeout of 5 seconds
    clientSocket = socket(AF_INET, SOCK_DGRAM)
    # clientSocket.setblocking(0)
    clientSocket.settimeout(3)

    file = open(filePath, "r")
    startTime = time()
    while True:
        try:
            tmpRTT = []
            # Slide window
            if send_base in waitingACK:
                tmpInx = waitingACK.index(send_base) + 1

                # when an Ack of a number is received, conclude the anyother ack of lower number
                for j in range(tmpInx):
                    delay = receivedTime[j] - delayACK[j]
                    delays.append(delay)
                    tmpRTT.append(delay)
                    throughputs.append(getsizeof(window[j]) / delay)
                    
                # slide
                waitingACK = waitingACK[tmpInx:]
                window = window[tmpInx:]
                delayACK = delayACK[tmpInx:]
                receivedTime = []
                
                if send_base not in cwndWindow:
                    cwndWindow = []
                else:
                    cwndWindow = cwndWindow[tmpInx:]
                
            # current window size
            lenWindow = len(window)
            
            # fill the window with packet
            while len(cwndWindow) < fixedSize:
                # get the first 1000 bytes of the file
                chunk = file.read(pocketSize)

                # while file is not empty
                if chunk:
                    # add a sequential tracking number to the packet
                    window.append((str(pocketNumber) + "|" + chunk))
                    waitingACK.append(pocketNumber)
                    cwndWindow.append(pocketNumber)
                    pocketNumber += 1
                else:
                    noData = True
                    break
                
            if not waitingACK and noData:
                break
            
            # print("Current Window: ", [int( headerNumber.search(x).group()) for x in window])
            print("Current Window: ", cwndWindow)
            if tmpRTT:
                print("Most recent RTT: ", delays[-1])
                rtt = max(tmpRTT)
            # print("(real)Current Window: ", waitingACK)
            
            # send a message to receiver
            for i in range(len(window) - lenWindow):
                responseQueue += 1
                delayACK.append(time())
                clientSocket.sendto(window[i+lenWindow].encode(), (serverName, serverPort))
                print("Sequence Number of Packet Sent: %d" %waitingACK[i+lenWindow])
                
            # get acknowledgment for this window
            sTime2 = max(0.4,(0.4*fixedSize/5))
            while responseQueue > 0:
                if select.select([clientSocket], [], [], sTime2)[0]:
                    modifiedMessage, serverAddress = clientSocket.recvfrom(1024)
                    currentTime = time()
                    responseQueue -= 1
                    currentResponse = int(modifiedMessage.decode())
                    if currentResponse > send_base:
                        for _ in range(currentResponse - send_base):
                            receivedTime.append(currentTime)
                    receivedACK.append(currentResponse)
                else:
                    responseQueue -= 1
                    break
            
            if receivedACK:
                for msg in receivedACK:
                    print("Acknowledgment Number Received: %d" %msg)
                send_base = max(receivedACK)
            
            # data lost or ACK lost happened
            if send_base < waitingACK[-1]:
                # Reduce ssthresh
                # ssthresh = fixedSize/2
                
                # Dup ACK threshold check
                count = receivedACK.count(send_base)
                
                if send_base in waitingACK:
                    base_index = waitingACK.index(send_base) + 1
                else:
                    base_index = 0
                    
                if send_base in previousResponse:
                    pCount = previousResponse.count(send_base)
                    count += pCount
                    
                # when receive 4 duplicate packets, do a fast transmission
                if count >= 4:
                    print("\n\n\n-------------------------")
                    print("(Dup) Sequence Number of Packet Sent: %d" %waitingACK[base_index])
                    clientSocket.sendto(window[base_index].encode(), (serverName, serverPort))
                    responseQueue += 1
                    fixedSize = int(fixedSize*0.5)
                    outBound = min((base_index + fixedSize), len(waitingACK))
                    cwndWindow = waitingACK[base_index:outBound]
                    
                # no Dup ACK but packet lost so timeout happen
                else:
                    timeV = 5 - (time()- (timeReset[1] if send_base == timeReset[0] else delayACK[base_index]))
                    
                    if timeV <= 0:
                        raise timeout
                    clientSocket.settimeout(timeV)
                    # check timeout
                    modifiedMessage, serverAddress = clientSocket.recvfrom(1024)
                    # if there is a data
                    print("\n\n\n\n\n\n\n\n Found")
                    currentTime = time()
                    currentResponse = int(modifiedMessage.decode())
                    if currentResponse > send_base:
                        for _ in range(currentResponse - send_base):
                            receivedTime.append(currentTime)
                        send_base = currentResponse
                        receivedACK.append(send_base)
                    print("(Found) Acknowledgment Number Received: %d" %currentResponse)
            # no data drop
            else:
                if rtt <= 0.5:
                    fixedSize += 2
                else:
                    if fixedSize > 2:
                        fixedSize -= 2
                        
                    
            # mark the packet number as "received"
            previousResponse = receivedACK
            receivedACK = []

        except timeout:
            print("\n\n\n-------------------------")
            print("(timeout) Sequence Number of Packet Sent: %d" %waitingACK[base_index])
            timeReset = [send_base, time()]
            clientSocket.sendto(window[base_index].encode(), (serverName, serverPort))
            responseQueue += 1
            previousResponse = receivedACK
            receivedACK = []
            fixedSize = int(fixedSize*0.5)
            outBound = min((base_index + fixedSize), len(waitingACK))
            cwndWindow = waitingACK[base_index:outBound]
            
        except ZeroDivisionError as err:
            break

    print("\n")
    print("Average Delay = ", sum(delays)*1000 / len(delays))
    print("Average Throughput = ", sum(throughputs)*8 / len(throughputs))
    print("Performance = ", log(sum(throughputs)*8 / len(throughputs), 10) - log(sum(delays)*1000 / len(delays), 10))
    print("total time =", (time()-startTime))
    clientSocket.close()

if __name__ == "__main__":
    main()