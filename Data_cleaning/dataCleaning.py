"""
Enhanced Functional Dependency Data Cleaner - Custom Version
Implements an 8-step cleaning process that preserves most columns but removes exact duplicates.
"""

import pandas as pd
import numpy as np
from fuzzywuzzy import process
"""File_handeling, argument_passing, regex"""
import os
import sys
import argparse
import re
from datetime import datetime


class FDCleaner:
    def __init__(self, file_path=None, df=None, encoding='latin-1'):
        """Initialize with file path or DataFrame"""
        self.modified_cols = set()
        self.removed_cols = set()

        # Load data
        if df is not None:
            self.df = df.copy()
        elif file_path:
            ext = os.path.splitext(file_path)[1].lower()
            if ext == '.csv':
                # Try with specified encoding, with fallbacks if needed
                try:
                    self.df = pd.read_csv(file_path, encoding=encoding)
                except UnicodeDecodeError:
                    # Try common encodings if the specified one fails
                    for enc in ['latin-1', 'cp1252', 'ISO-8859-1', 'utf-8-sig']:
                        if enc != encoding:  # Skip if it's the one we already tried
                            try:
                                self.df = pd.read_csv(file_path, encoding=enc)
                                print(f"Successfully read file with encoding: {enc}")
                                break
                            except UnicodeDecodeError:
                                continue
                    else:  # This runs if no encoding works
                        # Last resort: read with errors='replace'
                        self.df = pd.read_csv(file_path, encoding='latin-1', errors='replace')
                        print("Warning: Some characters couldn't be decoded properly")
            elif ext in ['.xlsx', '.xls']:
                self.df = pd.read_excel(file_path)
            else:
                raise ValueError("Only CSV or Excel files supported")
            self.file_path = file_path
        else:
            raise ValueError("Provide either file_path or df")

        # Store original column names for reference
        self.original_columns = list(self.df.columns)
        self.original_shape = self.df.shape
        self.log = []

        # Standardize column names immediately after loading
        self.standardize_column_names()

    def print_log(self, message):
        """Add message to log and print it"""
        print(message)
        self.log.append(message)

    def standardize_column_names(self):
        """Standardize column names (lowercase, replace spaces with underscores)"""
        rename_dict = {}

        for col in self.df.columns:
            # Convert to lowercase, replace spaces with underscores
            new_col = col.lower().strip()
            new_col = re.sub(r'\s+', '_', new_col)
            # Remove special characters except underscores
            new_col = re.sub(r'[^\w\d_]', '', new_col)
            # Ensure name is valid and unique
            rename_dict[col] = new_col

        # Handle duplicate column names after standardization
        seen = {}
        for old_col, new_col in rename_dict.items():
            if new_col in seen:
                rename_dict[old_col] = f"{new_col}_{seen[new_col]}"
                seen[new_col] += 1
            else:
                seen[new_col] = 1

        # Apply the renaming
        self.df.rename(columns=rename_dict, inplace=True)

        # Log the column renaming
        renamed_count = sum(1 for old, new in rename_dict.items() if old != new)
        if renamed_count > 0:
            self.print_log(f"Standardized {renamed_count} column names")
            for old, new in rename_dict.items():
                if old != new:
                    self.print_log(f"  - '{old}' → '{new}'")

    def clean_data(self):
        """Execute all 8 steps of data cleaning while preserving most columns"""
        self.print_log(f"Starting data cleaning: {self.original_shape[0]} rows, {self.original_shape[1]} columns")

        # Step 1: Remove duplicates
        initial_rows = len(self.df)
        self.df.drop_duplicates(inplace=True)
        self.print_log(f"✓ Removed {initial_rows - len(self.df)} duplicate rows")

        # Step 2: Handle missing values (fill with "null" instead of removing)
        missing_cols = self.df.columns[self.df.isna().any()].tolist()

        # Do not drop any columns with missing values, fill them instead
        for col in self.df.columns:
            if self.df[col].isna().any():
                missing_count = self.df[col].isna().sum()
                missing_pct = (missing_count / len(self.df)) * 100

                # Fill missing values with "null" or appropriate placeholders
                if pd.api.types.is_numeric_dtype(self.df[col]):
                    # For numeric columns, convert to nullable type and fill with "null"
                    self.df[col] = self.df[col].astype('object')
                    self.df[col].fillna("null", inplace=True)
                else:
                    self.df[col].fillna("null", inplace=True)

                self.modified_cols.add(col)
                self.print_log(f"  - Filled {missing_count} missing values ({missing_pct:.1f}%) in '{col}' with 'null'")

        if missing_cols:
            self.print_log(f"✓ Filled missing values in {len(missing_cols)} columns with 'null'")
        else:
            self.print_log("✓ No missing values found in the dataset")

        # Step 3: Standardize formats
        # Handle text columns
        text_cols = self.df.select_dtypes(include=['object']).columns
        for col in text_cols:
            # Convert to lowercase and strip whitespace (but skip "null" values)
            if not self.df[col].empty:
                # Only convert non-null values to lowercase
                self.df[col] = self.df[col].apply(
                    lambda x: x.lower().strip() if isinstance(x, str) and x != "null" else x
                )
                self.modified_cols.add(col)

        # Handle date columns
        date_cols = [col for col in self.df.columns if
                     any(term in col.lower() for term in ['date', 'time', '_at'])]
        for col in date_cols:
            try:
                # Create a temporary column to avoid modifying "null" values
                temp_col = pd.to_datetime(self.df[col], errors='coerce')
                if temp_col.notna().mean() > 0.8:  # If >80% valid
                    # Only format dates for non-null values
                    mask = temp_col.notna()
                    self.df.loc[mask, col] = temp_col.loc[mask].dt.strftime('%Y-%m-%d')
                    self.modified_cols.add(col)
            except:
                pass

        # Round floats
        for col in self.df.select_dtypes(include=['float']).columns:
            self.df[col] = self.df[col].round(2)
            self.modified_cols.add(col)

        self.print_log(f"✓ Standardized formats in {len(self.modified_cols)} columns")

        # Step 4: Fix inconsistent values
        # Find categorical columns with reasonable number of categories
        cat_cols = [col for col in text_cols if 1 < self.df[col].nunique() < 50]
        fixed_cols = 0

        for col in cat_cols:
            # Exclude "null" values from standardization
            unique_vals = [val for val in self.df[col].dropna().unique()
                          if val != "null" and isinstance(val, str)]

            if len(unique_vals) <= 1:
                continue

            # Find similar values with fuzzy matching
            changes = {}
            processed = set()

            for val in unique_vals:
                if val in processed:
                    continue

                # Find matches with 85% or higher similarity
                matches = process.extractBests(str(val),
                                             [str(v) for v in unique_vals],
                                             score_cutoff=85)

                if len(matches) > 1:
                    similar = [m[0] for m in matches]
                    # Use most frequent as standard
                    counts = self.df[col].value_counts()
                    try:
                        standard = counts.loc[similar].idxmax()
                    except:
                        standard = similar[0]

                    # Map similar values to standard
                    for match_val, _ in matches:
                        if match_val != standard:
                            changes[match_val] = standard
                            processed.add(match_val)
                    processed.add(standard)

            # Apply changes if found
            if changes:
                self.df[col] = self.df[col].replace(changes)
                self.modified_cols.add(col)
                fixed_cols += 1

        self.print_log(f"✓ Fixed inconsistent values in {fixed_cols} columns")

        # Step 5: Identify constant attributes (but don't remove them)
        # Find columns with only one unique value
        constant_cols = [col for col in self.df.columns
                        if self.df[col].nunique() == 1]

        if constant_cols:
            self.print_log(f"✓ Found {len(constant_cols)} constant columns (keeping all):")
            for col in constant_cols:
                self.print_log(f"  - '{col}' has only one value: {self.df[col].iloc[0]}")
        else:
            self.print_log("✓ No constant columns found")

        # Step 6: Remove redundant attributes (totally similar columns)
        # Find duplicate columns
        cols_to_drop = []
        duplicate_pairs = []

        for i, col1 in enumerate(self.df.columns):
            for col2 in self.df.columns[i+1:]:
                # Check if columns are identical
                if col1 not in cols_to_drop and col2 not in cols_to_drop:
                    if self.df[col1].equals(self.df[col2]):
                        cols_to_drop.append(col2)  # Keep the first column, drop the second
                        duplicate_pairs.append((col1, col2))

        # Actually drop redundant columns now
        if cols_to_drop:
            self.print_log(f"✓ Found {len(cols_to_drop)} duplicate columns to remove:")
            for col1, col2 in duplicate_pairs:
                self.print_log(f"  - Keeping '{col1}', removing '{col2}' (identical values)")

            self.df.drop(columns=cols_to_drop, inplace=True)
            self.removed_cols.update(cols_to_drop)
            self.print_log(f"✓ Removed {len(cols_to_drop)} duplicate columns")
        else:
            self.print_log("✓ No duplicate columns found")

        # Step 7: Verify key constraints
        # Find candidate keys
        key_candidates = [col for col in self.df.columns
                         if self.df[col].nunique() == len(self.df)]

        if key_candidates:
            self.print_log(f"✓ Found {len(key_candidates)} potential key columns:")
            for col in key_candidates:
                self.print_log(f"  - {col}")
        else:
            # Check for basic composite keys (pairs only)
            composite_found = False
            cols = self.df.columns.tolist()
            for i, col1 in enumerate(cols):
                if composite_found:
                    break
                for col2 in cols[i+1:]:
                    if not self.df.duplicated(subset=[col1, col2]).any():
                        self.print_log(f"✓ Found composite key: {col1} + {col2}")
                        composite_found = True
                        break

            if not composite_found:
                self.print_log("✓ No obvious key constraints found")

        # Step 8: Final consistency check
        # Check for any remaining missing values
        if "null" in self.df.values:
            null_count = (self.df == "null").sum().sum()
            self.print_log(f"✓ Dataset contains {null_count} 'null' values (placeholders for missing data)")

        # Check for duplicates
        dupes = self.df.duplicated().sum()
        if dupes > 0:
            self.print_log(f" Warning: {dupes} duplicate rows remain")
        else:
            self.print_log(" No duplicate rows in final dataset")

        # Final summary
        self.print_log(f"\n Cleaning complete!")
        self.print_log(f"Original: {self.original_shape[0]} rows, {self.original_shape[1]} columns")
        self.print_log(f"Cleaned:  {self.df.shape[0]} rows, {self.df.shape[1]} columns")
        self.print_log(f"Columns modified: {len(self.modified_cols)}")
        if self.removed_cols:
            self.print_log(f"Columns removed: {len(self.removed_cols)} (duplicate columns)")

        return self.df

    def save(self, output_path=None):
        """Save the cleaned dataset"""
        if output_path is None and hasattr(self, 'file_path'):
            base, ext = os.path.splitext(self.file_path)
            output_path = f"{base}_clean{ext}"
        else:
            output_path = output_path or "cleaned_data.csv"

        # Save based on file extension
        if output_path.lower().endswith('.csv'):
            self.df.to_csv(output_path, index=False, encoding='utf-8')
        elif output_path.lower().endswith(('.xlsx', '.xls')):
            self.df.to_excel(output_path, index=False)
        else:
            output_path = f"{output_path}.csv"
            self.df.to_csv(output_path, index=False, encoding='utf-8')

        self.print_log(f"✓ Cleaned dataset saved to: {output_path}")

        return output_path


def main():
    """Command line interface"""
    parser = argparse.ArgumentParser(
        description="Clean a dataset for functional dependency discovery (removes duplicate columns)")
    parser.add_argument('input_file', help='CSV or Excel file to clean')
    parser.add_argument('-o', '--output', help='Output file path')
    parser.add_argument('-e', '--encoding', default='latin-1',
                       help='File encoding (default: latin-1)')

    args = parser.parse_args()

    try:
        cleaner = FDCleaner(args.input_file, encoding=args.encoding)
        cleaner.clean_data()
        cleaner.save(args.output)
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
