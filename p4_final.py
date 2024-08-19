from socket import *
from sys import getsizeof
import select
from math import log
from time import time


def main():

    delays = []  # store pocket delay
    throughputs = []  # store size of packet
    filePath = "message.txt" # name of file

    serverName = gethostbyname(gethostname())  # local server
    pocketSize = 1000  # size of a pocket sent to server
    pocketNumber = 1  # tracking number of pockets sent to server
    
    window = []  # container of multiple packets send to receiver at a time
    waitingACK = [] # sequence number of packets in the window
    delayACK = []  # delays of packets in the window
    previousResponse = [] # save previous window to calculate the triple ACK accurately
    receivedTime = []  # Time list that saves the packet arriving time
    receivedACK = [] # ACK list that saves the packet ack response
    send_base = 0  # keep track highest ack received
    base_index = 0 # save window index of packet that should be resent
    duplicateACKThreshold = 4  # whenever we receive this number of duplicate ACK, do fast transmission
    responseQueue = 0  # number of packets in transaction
    noData = False # true if readfile is empty
    timeReset = [-1,0] # retransmission happen from the last window
    
    # Vegas, Reno, Custom setting
    fixedSize = 1  # window size
    cwndWindow = [] # display current window
    tmpRTT = [] # list to save RTTs of current window
    base_rtt = 0 # keep track minimum RTT
    rtt = 0 # save max RTT of current window
    dupFlag = False # tripe ACK flag
    outFlag = False # timeout flag
    TimeoutInterval = 5 # initial timeout
    EstimatedRTT = 0 # initial EstimatedRTT
    DevRTT = 0 # initial DevRTT
    alpha = 0.45 # max value to increase window size
    beta = 0.45 # min value to decrease window size

    # user input port
    serverPort = int(input("Enter the Port number you want your receiver to run: "))

    # setup a socket with timeout of 5 seconds
    clientSocket = socket(AF_INET, SOCK_DGRAM)
    clientSocket.settimeout(5)

    file = open(filePath, "r")
    
    while True:
        try:
            # window size calculate section
            # if dup ACK or timeout happen
            if dupFlag or outFlag:
                # if dup ACK happened
                if dupFlag:
                    # reduce window size by 3/4
                    # similar to Reno
                    fixedSize = int(fixedSize*0.75)
                    outBound = min((base_index + fixedSize), len(waitingACK))
                    if waitingACK:
                        cwndWindow = waitingACK[base_index:outBound]
                    else:
                        cwndWindow = []
                # if timeout happened
                else:
                    # reduce window size by 1
                    fixedSize = 1
                    if waitingACK:
                        cwndWindow = [waitingACK[base_index]]
                    else:
                        cwndWindow = []
            elif pocketNumber > 1:
                
                # get base_rtt and rtt 
                if tmpRTT:
                    rtt = max(tmpRTT)
                    if base_rtt != 0:
                        base_rtt = min(base_rtt, min(tmpRTT))
                    else:
                        base_rtt = min(tmpRTT)
                
                # calculate window size by RTT, similar to Vegas
                # with my custom variables alpha and beta
                diff = fixedSize/base_rtt - fixedSize/rtt
                
                # increase window size 
                if diff < alpha/base_rtt:
                    fixedSize += 1
                # decrease window size
                elif beta/base_rtt < diff:
                    fixedSize -= 1
            
            # reset flags and list
            dupFlag, outFlag = False, False
            resent_packet, receivedACK, tmpRTT = [], [], []
                
           # current window size before fill it
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
            
            # exit while loop if the window is empty and no more data to read
            if not waitingACK and noData:
                break
            
            # print current window
            print("\nCurrent Window: ", cwndWindow)
            
            # send a message to receiver
            for i in range(len(window) - lenWindow):
                responseQueue += 1
                delayACK.append(time())
                clientSocket.sendto(window[i+lenWindow].encode(), (serverName, serverPort))
                print("Sequence Number of Packet Sent: %d" %waitingACK[i+lenWindow])
                
            # calculate the timeout value for select.select by window size
            sTime2 = max(0.4,(0.4*fixedSize/5))
            
            # get acknowledgment for this window
            while responseQueue > 0:
                # if there is ACK in receiving buffer, retrive it
                if select.select([clientSocket], [], [], sTime2)[0]:
                    modifiedMessage, serverAddress = clientSocket.recvfrom(1024)
                    currentTime = time()
                    responseQueue -= 1
                    currentResponse = int(modifiedMessage.decode())
                    
                    # conclude delays for all unacknowledged packets equal and lower than received ACK
                    if currentResponse > send_base:
                        for _ in range(currentResponse - send_base):
                            receivedTime.append(currentTime)
                            
                    # save received ACKs for this window
                    receivedACK.append(currentResponse)
                    
                    # process acknowledgments received 
                    print("Acknowledgment Number Received: %d" %currentResponse)
                # in case there is no more data in buffer
                else:
                    responseQueue -= 1
                    break
                
                # Triple ACK check section below
                
                # keep track highest ACK received
                send_base = max(receivedACK)
                
                # count ACKs for current window
                count = receivedACK.count(send_base)
                  
                # check ACKs for previous window and count  
                if send_base in previousResponse:
                    pCount = previousResponse.count(send_base)
                    count += pCount

                # when receive 4 duplicate packets, first resending, and not the end of the window
                # do a fast transmission
                if count >= duplicateACKThreshold and send_base not in resent_packet and send_base < waitingACK[-1]:
                    # get the index of retransmission packet
                    if send_base in waitingACK:
                        base_index = waitingACK.index(send_base) + 1
                    else:
                        base_index = 0
                    
                    print("Sequence Number of Packet Sent: %d" %waitingACK[base_index])
                    clientSocket.sendto(window[base_index].encode(), (serverName, serverPort))
                    responseQueue += 1
                    resent_packet.append(send_base)
                    dupFlag = True
                    
            # Slide Window and calculate TimeoutInterval section
            if send_base in waitingACK:
                # calculate how many packet received
                tmpInx = waitingACK.index(send_base) + 1
                
                # calculate delay and throughput for each packet received
                # save RTT in tmpRTT to calculate window size later
                for j in range(tmpInx):
                    delay = receivedTime[j] - delayACK[j]
                    delays.append(delay)
                    tmpRTT.append(delay)
                    throughputs.append(getsizeof(window[j]) / delay)
                    
                    # TimeoutInterval calculation when packet sequence is 1
                    if 1 in waitingACK and j == 0:
                        EstimatedRTT = receivedTime[0] - delayACK[0]
                        TimeoutInterval = EstimatedRTT
                    # TimeoutInterval calculation when packet sequence other than 1
                    else:
                        sampleRTT = delay
                        DevRTT = DevRTT*0.75 + abs(sampleRTT - EstimatedRTT)*0.25
                        EstimatedRTT = EstimatedRTT*0.875 + sampleRTT*0.125
                        TimeoutInterval = EstimatedRTT + DevRTT*4
                    
                # remove received packets from window
                waitingACK = waitingACK[tmpInx:]
                window = window[tmpInx:]
                delayACK = delayACK[tmpInx:]
                receivedTime = []
            
                if send_base not in cwndWindow:
                    cwndWindow = []
                else:
                    cwndWindow = cwndWindow[tmpInx:]
            
            # save current received ACKs
            previousResponse = receivedACK
            
            # if we don't not receive the lastest ACK of the window, check whether there is packet loss
            if waitingACK:
                
                # get the index of retransmission packet
                if send_base in waitingACK:
                    base_index = waitingACK.index(send_base) + 1
                else:
                    base_index = 0
                    
                # maintain the refinement of the timeout within 5 sec in this iteration
                # after 5 secs since we send the packet, call timeout
                
                # calculate timer based on the time that packet has sent or resent
                timeV = TimeoutInterval - (time()- (timeReset[1] if send_base == timeReset[0] else delayACK[base_index]))
                
                if timeV <= 0:
                    raise timeout
                
                clientSocket.settimeout(timeV)
                
                # check any upcoming ACK until timeout
                modifiedMessage, serverAddress = clientSocket.recvfrom(1024)
                
                # if receive ack before timeout, do same process to save response time
                currentTime = time()
                currentResponse = int(modifiedMessage.decode())
                print("Acknowledgment Number Received: %d" %currentResponse)
                if currentResponse > send_base:
                    for _ in range(currentResponse - send_base):
                        receivedTime.append(currentTime)
                    send_base = currentResponse
                    receivedACK.append(send_base)
                # save current received ACKs
                previousResponse = receivedACK
                
                # Slide Window and calculate TimeoutInterval
                if send_base in waitingACK:
                    
                    # calculate how many packet received
                    tmpInx = waitingACK.index(send_base) + 1
                    
                    # calculate delay and throughput for each packet received
                    # save RTT in tmpRTT to calculate window size later
                    for j in range(tmpInx):
                        delay = receivedTime[j] - delayACK[j]
                        delays.append(delay)
                        tmpRTT.append(delay)
                        throughputs.append(getsizeof(window[j]) / delay)
                        
                        # TimeoutInterval calculation when packet sequence is 1
                        if 1 in waitingACK and j == 0:
                            EstimatedRTT = receivedTime[0] - delayACK[0]
                            TimeoutInterval = EstimatedRTT
                        # TimeoutInterval calculation when packet sequence other than 1
                        else:
                            sampleRTT = delay
                            DevRTT = DevRTT*0.75 + abs(sampleRTT - EstimatedRTT)*0.25
                            EstimatedRTT = EstimatedRTT*0.875 + sampleRTT*0.125
                            TimeoutInterval = EstimatedRTT + DevRTT*4
                        
                    # remove received packets from window
                    waitingACK = waitingACK[tmpInx:]
                    window = window[tmpInx:]
                    delayACK = delayACK[tmpInx:]
                    receivedTime = []
                
                    if send_base not in cwndWindow:
                        cwndWindow = []
                    else:
                        cwndWindow = cwndWindow[tmpInx:]

        # when timeout is raised, resend a packet
        except timeout:
            print("Sequence Number of Packet Sent: %d" %waitingACK[base_index])
            # save resent time to reset the timer
            timeReset = [send_base, time()]
            clientSocket.sendto(window[base_index].encode(), (serverName, serverPort))
            # increase response loop count and flag on
            responseQueue += 1
            outFlag = True
            
        except ZeroDivisionError as err:
            break

    # convert second to millisecond and byte to bits
    delays = [second * 1000 for second in delays]
    throughputs = [byte * 8 for byte in throughputs]
    
    # report performance
    print("\n")
    print("Average Delay = ", sum(delays) / len(delays), " milliseconds")
    print("Average Throughput = ", sum(throughputs) / len(throughputs), " bits per second")
    print("Performance = ", log(sum(throughputs) / len(throughputs), 10) - log(sum(delays) / len(delays), 10))
    clientSocket.close()

if __name__ == "__main__":
    main()