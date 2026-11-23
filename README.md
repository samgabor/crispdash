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

## Environment configuration (.env)

Create a file named `.env` in the project root, alongside `app.py`. Specify all
seven settings below, replacing the example values with your own:

```dotenv
NCBI_API_KEY=YOUR-NCBI-API-KEY
NCBI_EMAIL=you@example.com
AZURE_TENANT_ID=YOUR-TENANT-ID
AZURE_CLIENT_ID=YOUR-APPLICATION-ID
AZURE_CLIENT_SECRET=YOUR-CLIENT-SECRET
AGENT_NAME=CRISPOR-Expert
PROJECT_ENDPOINT=https://YOUR-RESOURCE.services.ai.azure.com/api/projects/YOUR-PROJECT
```

- `NCBI_API_KEY`: your NCBI API key for NCBI/ClinVar requests.
- `NCBI_EMAIL`: your contact email for NCBI services.
- `AZURE_TENANT_ID`: the Microsoft Entra tenant containing your application registration.
- `AZURE_CLIENT_ID`: the application (client) ID of that registration.
- `AZURE_CLIENT_SECRET`: the client secret **value**, not its secret ID.
- `AGENT_NAME`: the name of the existing Foundry agent to invoke.
- `PROJECT_ENDPOINT`: the Foundry project endpoint, including `/api/projects/YOUR-PROJECT`;
  do not append the agent or protocol path—the dashboard adds those automatically.

The Entra application must have permission to invoke the agent. All five Azure
settings must be present and nonblank for Expert Chat to appear; the annotation
dashboard remains available without Expert Chat configuration.

Keep `.env` private and do not commit it to version control. Restart Streamlit
after changing these settings. Settings may also be supplied through the server
environment.

## Usage

Run the application:

```bash
python -m streamlit run app.py
```

## Optional Expert Chat (Azure Foundry)

Expert Chat appears after Evidence Summary when the five Azure settings in
[Environment configuration](#environment-configuration-env) are nonblank.

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
