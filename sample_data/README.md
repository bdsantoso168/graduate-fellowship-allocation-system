# Sample Data

This folder contains completely fictional sample files for demonstration and testing.

**No real student records, resumes, or personally identifiable information is included.**

## How to use
1. Upload `sample_roster.csv` on the Upload Data step.
2. Create a ZIP of sample resume PDFs named by UID (e.g. `UID00000001_Alex_Rivera.pdf`) and upload it.
3. The app will extract and match them through the pipeline.

## Required CSV columns
| Column         | Description                             | Required |
|----------------|-----------------------------------------|----------|
| uid            | Unique student identifier (e.g. UID001) | Yes      |
| first_name     | Student first name                      | Yes      |
| last_name      | Student last name                       | Yes      |
| degree_program | Graduate degree (e.g. MS in Finance)    | Yes      |
| gpa            | GPA on a 4.0 scale                      | Yes      |
| email          | Contact email                           | No       |
