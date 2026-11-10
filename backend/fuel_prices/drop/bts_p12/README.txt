BTS monthly fuel table drop folder
1. Download the monthly table from https://www.transtats.bts.gov/fuel.asp (Airline Fuel Cost and Consumption, U.S. Carriers - Scheduled) as CSV, yourself, in your browser.
2. Put the .csv in this folder and make sure column_map.json names its columns (see column_map.example.json). Pick the aggregate OR the individual carriers, never both
   (use carrier_exclude for aggregate rows such as "All Majors").
3. Enable "BTS P-12(a) monthly fuel" in Fuel Statistics > Data coverage & sources (needs your sign-off). The app imports the file within the hour and moves it to processed/.
   A file it cannot read goes to failed/ with a .error.txt explaining why.
