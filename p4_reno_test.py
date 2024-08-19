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
    duplicateACKThreshold = 4  # whenever we receive this number of duplicate ACK, do fast transmission
    responseQueue = 0  # number of packets in transaction
    noData = False # true if readfile is empty
    timeReset = [-1,0] # retransmission happen from the last iteration
    
    # Tahoe setting
    fixedSize = 1  # window size
    ssthresh = 16
    TimeoutInterval = 5
    EstimatedRTT = 0
    DevRTT = 0
    cwndWindow = []
    dupFlag = False
    outFlag = False

    # user input port
    serverPort = int(input("Enter the Port number you want your receiver to run: "))

    # setup a socket with timeout of 5 seconds
    clientSocket = socket(AF_INET, SOCK_DGRAM)
    clientSocket.settimeout(5)

    file = open(filePath, "r")
    startTime = time()
    while True:
        try:
            if dupFlag or outFlag:
                # Reduce ssthresh
                ssthresh = fixedSize/2
                
                # penalty run
                if dupFlag:
                    fixedSize = int(fixedSize*0.5)
                    outBound = min((base_index + fixedSize), len(waitingACK))
                    if waitingACK:
                        cwndWindow = waitingACK[base_index:outBound]
                    else:
                        cwndWindow = []
                else:
                    fixedSize = 1
                    if waitingACK:
                        cwndWindow = [waitingACK[base_index]]
                    else:
                        cwndWindow = []
            elif pocketNumber > 1:
                if fixedSize >= ssthresh:
                    fixedSize += 1
                else:
                    fixedSize = fixedSize*2
                    
            dupFlag, outFlag = False, False
            dup_ack, receivedACK = [], []
                
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
            
            print("Current Window: ", cwndWindow)
            
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
                    
                    # process acknowledgments received 
                    print("Acknowledgment Number Received: %d" %currentResponse)
                else:
                    responseQueue -= 1
                    break
                
                # Fast retransmit check below ------------------------
                send_base = max(receivedACK)
                
                # Dup ACK threshold check
                count = receivedACK.count(send_base)
                    
                if send_base in previousResponse:
                    pCount = previousResponse.count(send_base)
                    count += pCount

                # when receive 4 duplicate packets, do a fast transmission
                if count >= duplicateACKThreshold and send_base not in dup_ack and send_base < waitingACK[-1]:
                    # tracking the total number of ACK have been received
                    if send_base in waitingACK:
                        base_index = waitingACK.index(send_base) + 1
                    else:
                        base_index = 0
                    # print("\n\n\n-------------------------")
                    print("(Dup) Sequence Number of Packet Sent: %d" %waitingACK[base_index])
                    clientSocket.sendto(window[base_index].encode(), (serverName, serverPort))
                    responseQueue += 1
                    dup_ack.append(send_base)
                    dupFlag = True
            
            # Slide Window and calculate TimeoutInterval
            if send_base in waitingACK:
                
                tmpInx = waitingACK.index(send_base) + 1
                
                for j in range(tmpInx):
                    delay = receivedTime[j] - delayACK[j]
                    delays.append(delay)
                    throughputs.append(getsizeof(window[j]) / delay)
                    
                    if 1 in waitingACK and j == 0:
                        EstimatedRTT = receivedTime[0] - delayACK[0]
                        TimeoutInterval = EstimatedRTT
                    else:
                        sampleRTT = delay
                        DevRTT = DevRTT*0.75 + abs(sampleRTT - EstimatedRTT)*0.25
                        EstimatedRTT = EstimatedRTT*0.875 + sampleRTT*0.125
                        TimeoutInterval = EstimatedRTT + DevRTT*4
                    
                # slide
                waitingACK = waitingACK[tmpInx:]
                window = window[tmpInx:]
                delayACK = delayACK[tmpInx:]
                receivedTime = []
            
                if send_base not in cwndWindow:
                    cwndWindow = []
                else:
                    cwndWindow = cwndWindow[tmpInx:]
            
            # data lost or ACK lost happened
            if waitingACK:
                # mark the packet number as "received"
                previousResponse = receivedACK
                
                if send_base in waitingACK:
                    base_index = waitingACK.index(send_base) + 1
                else:
                    base_index = 0
                    
                # maintain the refinement of the timeout whin 5 sec in this iteration
                # after 5 secs since we send the window, call timeout
                timeV = TimeoutInterval - (time()- (timeReset[1] if send_base == timeReset[0] else delayACK[base_index]))
                    
                if timeV <= 0:
                    raise timeout
                
                clientSocket.settimeout(timeV)
                
                # check any upcoming ACK until timeout
                modifiedMessage, serverAddress = clientSocket.recvfrom(1024)
                
                currentTime = time()
                currentResponse = int(modifiedMessage.decode())
                print("Acknowledgment Number Received: %d" %currentResponse)
                if currentResponse > send_base:
                    for _ in range(currentResponse - send_base):
                        receivedTime.append(currentTime)
                    send_base = currentResponse
                    receivedACK.append(send_base)
                # mark the packet number as "received"
                previousResponse = receivedACK
                
                # Slide Window and calculate TimeoutInterval
                if send_base in waitingACK:
                    
                    tmpInx = waitingACK.index(send_base) + 1
                    
                    for j in range(tmpInx):
                        delay = receivedTime[j] - delayACK[j]
                        delays.append(delay)
                        throughputs.append(getsizeof(window[j]) / delay)
                        
                        if 1 in waitingACK and j == 0:
                            EstimatedRTT = receivedTime[0] - delayACK[0]
                            TimeoutInterval = EstimatedRTT
                        else:
                            sampleRTT = delay
                            DevRTT = DevRTT*0.75 + abs(sampleRTT - EstimatedRTT)*0.25
                            EstimatedRTT = EstimatedRTT*0.875 + sampleRTT*0.125
                            TimeoutInterval = EstimatedRTT + DevRTT*4
                        
                    # slide
                    waitingACK = waitingACK[tmpInx:]
                    window = window[tmpInx:]
                    delayACK = delayACK[tmpInx:]
                    receivedTime = []
                
                    if send_base not in cwndWindow:
                        cwndWindow = []
                    else:
                        cwndWindow = cwndWindow[tmpInx:]

        except timeout:
            print("\n\n\n-------------------------")
            print("(timeout) Sequence Number of Packet Sent: %d" %waitingACK[base_index])
            timeReset = [send_base, time()]
            clientSocket.sendto(window[base_index].encode(), (serverName, serverPort))
            responseQueue += 1
            outFlag = True
            
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