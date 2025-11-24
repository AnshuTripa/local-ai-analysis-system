import os
import pandas as pd

def save_cleaned_files(data_folder, output_folder):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    try:
        for file in os.listdir(data_folder):
            if file.endswith(".xlsx"):
                df = pd.read_excel(os.path.join(data_folder, file))
                df.to_excel(os.path.join(output_folder, file), index=False)

        return "✔ All cleaned files exported successfully."

    except Exception as e:
        return f"Export Error: {e}"
