# crispr-offtarget-dashboard
# A python dashboard project for exploring CRISPR Off-Target Sites

A dashboard for exploring CRISPR Off-Target Sites

## Requirements

- Python 3.14+
- pip

## Installation

Clone the repository:

```bash
git clone https://github.com/samgabor/crispdash.git
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

Run the application:

```bash
python -m streamlit run app.py
```

## Optional Expert Chat (Azure Foundry)

Expert Chat appears after Evidence Summary when all five settings below are
nonblank in the local `.env` file (or the server environment):

```dotenv
PROJECT_ENDPOINT=https://YOUR-RESOURCE.services.ai.azure.com/api/projects/YOUR-PROJECT
AGENT_NAME=CRISPOR-Expert
AZURE_TENANT_ID=YOUR-TENANT-ID
AZURE_CLIENT_ID=YOUR-APPLICATION-ID
AZURE_CLIENT_SECRET=YOUR-CLIENT-SECRET
```

Install the updated requirements and restart Streamlit after changing configuration.
Do not commit `.env`. The Entra application must have access to invoke the agent.
The agent's grounding document and research tools are configured in Foundry.
The dashboard does not create agents or upload the grounding document.

After analyzing a site, select Expert Chat and **Generate Site Assessment**.
No agent request is made automatically. The prepared evidence can be inspected
before sending. Failed annotation lookups are identified to the user and agent.
Large evidence lists are sampled (25 items per list), long text is shortened,
and omissions are recorded in the packet; full records stay in the annotation tabs.
Chat uses the agent's Responses endpoint, retaining both the previous response ID
and any returned agent session ID. Conversations are kept per guide/site in the
browser's Streamlit session, not shared across users or saved to disk. Evidence is
frozen for each conversation; start a new conversation to use refreshed evidence
or changed filters. Reset clears the local history and starts new response/session
IDs; it does not delete conversation data retained by Azure.

Agent responses are research support and must be checked against their sources.
The dashboard's provided evidence alone cannot establish whether a site is safe.

## License

See LICENSE for details.
