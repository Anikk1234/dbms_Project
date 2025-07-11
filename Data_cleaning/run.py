import cleaner

from dataCleaning import FDCleaner

if __name__ == "__main__":
    try:
        # Try with different encodings
        try:
            cleaner = FDCleaner("electric_vehicles_spec_2025.csv", encoding='latin-1')
        except UnicodeDecodeError:
            cleaner = FDCleaner("electric_vehicles_spec_2025.csv", encoding='cp1252')

        cleaned_df = cleaner.clean_data()
        cleaner.save("electric_vehicles_spec_2025_cleaned.csv")
        print("Cleaning completed successfully!")
    except Exception as e:
        print(f"Error during cleaning: {e}")