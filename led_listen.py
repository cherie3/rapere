import pyaudio
import wave
import RPi.GPIO as GPIO
import time
import webrtcvad
import requests
from secret import token_nondev as token

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
RECORD_SECONDS = 1
CHUNK = 320
INPUT_DEVICE = 2
SHORT_NORMALIZE = (10.0/32768.0)
LEDPIN = 16


def setup_pins():
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(LEDPIN, GPIO.OUT)
    GPIO.setwarnings(False)
    GPIO.output(LEDPIN, GPIO.LOW)


def setup_audio():
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    input_device_index=INPUT_DEVICE,
                    rate=RATE,
                    input=True,
                    output=False,
                    frames_per_buffer=CHUNK)
    vad = webrtcvad.Vad()
    vad.set_mode(3) # aggressiveness is 0=least to 3=highest
    print("* setup")
    return stream, p, vad


def flash(period):
    GPIO.output(LEDPIN, GPIO.HIGH)
    print('LED on ({})'.format(period))
    time.sleep(period)
    GPIO.output(LEDPIN, GPIO.LOW)


def led_on():
    GPIO.output(LEDPIN, GPIO.HIGH)
    print('LED on')


def led_off():
    GPIO.output(LEDPIN, GPIO.LOW)


def get_data(stream):
    data = stream.read(CHUNK, exception_on_overflow=False)
    return data


def write_file(frames, count, p):
    print("Writing to file")
    filename = 'out{}.wav'.format(count)
    wf = wave.open(filename, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()
    count += 1
    return filename, count


def transcribe(filename, token):
    #posts a recording to koreromaori.io - requires the filename to
    # be the same as the filepath ie audio is in the same folder as this code
    api_url = "https://koreromaori.io/api/transcription/?method=stream"
    kwargs = {
        'headers': {
            'Authorization': 'Token {0}'.format(token)
        },
        'files': {
            'audio_file': open(filename, 'rb')
        },
        'data': {
            'name': filename
        }
    }
    response = requests.post(api_url, **kwargs)
    response_dict = response.json()

    if response.status_code == 201:
        return response_dict.get('transcription')
    else:
        return -1


def look_for_words(words):
    result = 0
    for i in range(len(words)):
        if words[i] == 'kia' and words[i+1] == 'ora':
            result = 1
    return result


def finish(stream, p):
    stream.stop_stream()
    stream.close()
    p.terminate()
    GPIO.cleanup()
    print('closing')


def main():
    setup_pins()
    (stream, p, vad) = setup_audio()
    count = 0
    quiet_count = 0
    loud_count = 0
    frames = []

    while 1:
        try:
            frame = get_data(stream)
            contains_speech = vad.is_speech(frame, RATE)

            if contains_speech:
                loud_count += 1
                if quiet_count != 0:
                    quiet_count = 0
                frames.append(frame)
                    
            elif contains_speech == 0:
                if loud_count < 8 and quiet_count > 2 and frames != []:
                    loud_count = 0
                    frames = []
                quiet_count += 1

                if quiet_count > 20 and loud_count != 0:
                    frames = []
                    loud_count = 0

                if quiet_count >= 6 and loud_count > 20 and frames != []:
                    audio_file, count = write_file(frames, count, p)
                    frames = []
                    loud_count = 0
                    unsplit_words = transcribe(audio_file, token)
                    print(unsplit_words)
                    words = unsplit_words.split(" ")
                    in_dict = look_for_words(words)
                    print('------------------', words, '------------------')
                    if in_dict:
                        flash(10)
        except Exception as e:
            finish(stream, p)
            print('exception:  ', e)
            break

    finish(stream, p)
    print("* done recording")



main()
