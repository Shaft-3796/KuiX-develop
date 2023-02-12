import threading
import time

semaphore = threading.Semaphore(0)


def rlock():
    print("Rlock do stuff..")
    print("Rlock wait for the semaphore..")
    semaphore.acquire()
    print("Rlock released and do stuff..")


# Function to release the lock from a thread
def release_thread():
    semaphore.release()
    print("Semaphore released")


# Create 2 threads that lock the thread
t1 = threading.Thread(target=rlock)
t2 = threading.Thread(target=release_thread)

# Wait for all threads to finish
t1.start()
time.sleep(2)
t2.start()
t1.join()
t2.join()
