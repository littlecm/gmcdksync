import streamlit as st
import pandas as pd

# Expected column structures
expected_columns_cdk = ['VIN', 'Stock #', 'Stock  Type', 'Status', 'Deal  No.', 'Balance']
expected_columns_d2c2 = ['VIN', 'Stock #', 'Status']
expected_columns_removed = ['STOCK-NO.', 'STATUS']

# Function to check if the uploaded files have the expected columns
def validate_columns(uploaded_df, expected_columns, file_name):
    missing_columns = [col for col in expected_columns if col not in uploaded_df.columns]
    if missing_columns:
        st.error(f"Error: The uploaded {file_name} file is missing the following columns: {', '.join(missing_columns)}")
        return False
    return True

# Function to handle file uploads and processing
def process_files(cdk_file, d2c2_file, removed_file):
    # Load the CSV files
    cdk_df = pd.read_csv(cdk_file)
    d2c2_df = pd.read_csv(d2c2_file)
    removed_df = pd.read_csv(removed_file)

    # Standardize column names to avoid conflicts and remove extra spaces
    cdk_df.rename(columns={'Stock #': 'Stock # CDK', 'Deal  No.': 'Deal No.', 'Stock  Type': 'Stock Type', 'Status': 'Status_CDK'}, inplace=True)
    d2c2_df.rename(columns={'Stock #': 'Stock # D2C2', 'Status': 'Status_D2C2'}, inplace=True)
    removed_df.rename(columns={'STOCK-NO.': 'Stock # Removed', 'STATUS': 'Status_Removed'}, inplace=True)

    # Merge the two original dataframes on the VIN column, keeping all columns from both (outer join)
    merged_df = pd.merge(cdk_df, d2c2_df, how='outer', on='VIN', suffixes=('_CDK', '_D2C2'))

    # Create a new column to indicate whether the VIN is in both sources, only CDK, or only D2C2
    def source_designation(row):
        if pd.notna(row['Stock # CDK']) and pd.notna(row['Stock # D2C2']):
            return 'Appearing in both sources'
        elif pd.notna(row['Stock # CDK']) and pd.isna(row['Stock # D2C2']):
            return 'Appearing only in CDK'
        elif pd.isna(row['Stock # CDK']) and pd.notna(row['Stock # D2C2']):
            return 'Appearing only in D2C2'
        return 'Unknown'  # In case there are rows with missing VINs

    merged_df['Source Designation'] = merged_df.apply(source_designation, axis=1)

    # Function to evaluate each criteria and return unmet conditions or designation for missing vehicles
    def check_criteria(row):
        unmet_conditions = []
        
        if row['Stock Type'] not in ['NEW', 'USED', 'F']:
            unmet_conditions.append('Stock Type')
        
        if row['Status_CDK'] not in ['S', 'T']:
            unmet_conditions.append('Status')
        
        if pd.notna(row['Deal No.']):
            unmet_conditions.append('Deal No. is not empty')
        
        if pd.isna(row['Balance']) or float(row['Balance'].replace('$', '').replace(',', '')) <= 0:
            unmet_conditions.append('Balance > $0')
        
        if row['Status_D2C2'] == 'InTransit':
            unmet_conditions.append('D2C2 Status InTransit')

        return '; '.join(unmet_conditions) if unmet_conditions else 'Meets all criteria'

    # Apply the criteria check function and add the result to the Issues column
    merged_df['Criteria Check'] = merged_df.apply(check_criteria, axis=1)

    # Identify vehicles expected to be in both sources, excluding those with D2C2 Status 'InTransit'
    expected_criteria = (
        (merged_df['Stock Type'].isin(['NEW', 'USED', 'F'])) &
        (merged_df['Status_CDK'].isin(['S', 'T'])) &
        (merged_df['Balance'].apply(lambda x: float(x.replace('$', '').replace(',', '')) if pd.notna(x) else 0) > 0) &
        (merged_df['Deal No.'].isna()) &
        (merged_df['Status_D2C2'] != 'InTransit')
    )

    # Identify vehicles that meet the criteria and appear in both sources
    merged_df['Expected in Both Sources'] = expected_criteria & merged_df['Stock # D2C2'].notna()

    # Merge the removed_df with the vehicles only found in D2C2
    only_in_d2c2 = merged_df[merged_df['Source Designation'] == 'Appearing only in D2C2']
    reconciled_df = pd.merge(only_in_d2c2, removed_df, left_on='Stock # D2C2', right_on='Stock # Removed', how='left')

    # Add a column to indicate if there's a match and if the status is "G"
    reconciled_df['Removed Match Status'] = reconciled_df.apply(
        lambda row: 'Match and G' if pd.notna(row['Stock # Removed']) and row['Status_Removed'] == 'G' 
        else 'Match but not G' if pd.notna(row['Stock # Removed']) 
        else 'No Match', 
        axis=1
    )

    # Update Criteria Check for specific cases
    def update_criteria_check(row):
        if row['Source Designation'] == 'Appearing only in D2C2' and row['Removed Match Status'] == 'Match and G':
            return 'G Status in CDK'
        return row['Criteria Check']

    reconciled_df['Criteria Check'] = reconciled_df.apply(update_criteria_check, axis=1)

    # Combine the reconciled information back into the main dataframe
    merged_df = pd.concat([merged_df[merged_df['Source Designation'] != 'Appearing only in D2C2'], reconciled_df])

    # Sort by the expected criteria and VIN
    merged_df.sort_values(by=['Expected in Both Sources', 'VIN'], ascending=[False, True], inplace=True)
    
    return merged_df

# Streamlit app layout
st.title("VIN Data Reconciliation Tool")

st.write("Upload the CDK, D2C2, and Removed vehicle CSV files to begin.")

# Display expected structure for each file
st.subheader("Expected Column Structure")
st.write("### CDK CSV Expected Columns")
st.write(expected_columns_cdk)

st.write("### D2C2 CSV Expected Columns")
st.write(expected_columns_d2c2)

st.write("### Removed Vehicles CSV Expected Columns")
st.write(expected_columns_removed)

cdk_file = st.file_uploader("Upload CDK CSV", type=["csv"])
d2c2_file = st.file_uploader("Upload D2C2 CSV", type=["csv"])
removed_file = st.file_uploader("Upload Removed Vehicles CSV", type=["csv"])

if cdk_file and d2c2_file and removed_file:
    cdk_df = pd.read_csv(cdk_file)
    d2c2_df = pd.read_csv(d2c2_file)
    removed_df = pd.read_csv(removed_file)

    valid_cdk = validate_columns(cdk_df, expected_columns_cdk, "CDK")
    valid_d2c2 = validate_columns(d2c2_df, expected_columns_d2c2, "D2C2")
    valid_removed = validate_columns(removed_df, expected_columns_removed, "Removed Vehicles")

    if valid_cdk and valid_d2c2 and valid_removed:
        merged_df = process_files(cdk_file, d2c2_file, removed_file)
        
        st.write("### Merged Data")
        st.dataframe(merged_df)

        # Option to download the merged dataframe as a CSV file
        csv = merged_df.to_csv(index=False).encode('utf-8')
        st.download_button(label="Download Merged CSV", data=csv, file_name='merged_vin_data.csv', mime='text/csv')

else:
    st.warning("Please upload all three CSV files to proceed.")
