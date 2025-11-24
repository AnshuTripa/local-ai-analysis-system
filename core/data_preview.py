from tabulate import tabulate

def preview_cleaned_data(df):
    try:
        sample = df.head(20)
        return tabulate(sample, headers="keys", tablefmt="psql", showindex=False)
    except:
        return "Unable to print preview."
