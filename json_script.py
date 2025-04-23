from flask import Flask, request
from datetime import datetime
import json

# Initialize the Flask app
app = Flask(__name__)

# Route to handle incoming data
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        # Call the function to handle data when receiving a POST request
        return receive_data()
    return "GET request for /upload"

def receive_data():
    # Step 1: Get the incoming JSON data
    data = request.get_json()

    # Step 2: Add a timestamp to the data
    timestamp = datetime.now().isoformat()

    # Print the received data (for debugging purposes)
    print(f"\n[{timestamp}] Data received:")
    print(json.dumps(data, indent=2))

    # Step 3: Save the data to a file
    with open("/home/gvetters/test_folder/counter_data/particle_data_log.json", "a") as f:
        # Write the timestamped data to the file
        f.write(json.dumps({"timestamp": timestamp, "data": data}) + "\n")

    # Step 4: Respond to the counter that the data was received
    return "OK", 200  # You can change the message if needed

# Run the app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
