# Flexible Site Mapping Tool

A Streamlit mapping app that lets users upload a site file and dynamically control map styling and filters.

## What it does

The app accepts a CSV or Excel file with:

- `site code`
- `lat`
- `long`
- Up to four additional dimension columns with any names

Example dimension columns:

- `Senior buyer`
- `Role Spend`
- `Yes or No`
- `Dimension 4 Placeholder`

The user can then:

- Map all valid site latitude/longitude points
- Select which field controls point color
- Choose custom colors for categorical color values
- Select which field controls point shape
- Filter by site code
- Filter by every available dimension field
- Download the filtered dataset

## Files

- `app.py` — main Streamlit application
- `requirements.txt` — Python dependencies for Streamlit Cloud
- `sample_upload.csv` — sample upload file with flexible dimension columns
- `.gitignore` — standard Python/Streamlit ignore file

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy to Streamlit Cloud from GitHub

1. Create a new GitHub repository.
2. Upload these files into the repository root:
   - `app.py`
   - `requirements.txt`
   - `sample_upload.csv`
   - `.gitignore`
3. Go to Streamlit Community Cloud.
4. Select **New app**.
5. Connect the GitHub repo.
6. Set the main file path to:

```text
app.py
```

7. Deploy.

## Upload file rules

The app looks for the required columns case-insensitively and supports these aliases:

| Required field | Accepted examples |
|---|---|
| `site code` | `site code`, `site_code`, `site`, `site id`, `site_id`, `store`, `store number` |
| `lat` | `lat`, `latitude` |
| `long` | `long`, `lng`, `lon`, `longitude` |

Only the first four non-required columns are treated as flexible dimension fields.

## Notes

- Categorical color fields allow user-selected colors by category.
- Numeric color fields with many unique values use a continuous color scale.
- Shape styling depends on Plotly's supported map symbols. Very high-cardinality shape fields may create a crowded legend, so shape fields work best with low-cardinality dimensions.
