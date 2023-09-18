# Google Drive Service

Based on <https://www.labnol.org/google-api-service-account-220404>.

## Initial Setup

### 1. Create a Google Cloud Project

Go to Google Cloud Console <https://console.cloud.google.com> and create a new Google Cloud project. Give your project a name, change the project ID and click the `Create` button.

For tools in this repository, a project `PiBaseDemo` has been already created.

### 2. Enable Google APIs

Choose `APIs & Services` from the left menu and click on `Enable APIs and Services` to enable the various Google APIs. If you planning to upload files to Google Drive then you will need to enable `Drive API`. If you wish to use the Google Cloud Storage API then you will need to enable `Storage API`. Current implementation in `gd_service.py` uses only `Drive API`.

## New Location Setup

For each new deployment site / location, create a new Service Account.

### 1. Create a Service Account

Go to Google Cloud Console <https://console.cloud.google.com> and select the Project `PiBaseDemo`.

In the `APIs & Services` section, click on [`Credentials`](https://console.cloud.google.com/apis/credentials?project=pibasedemo) and click on `Create Credentials` and select `Service Account`.

Give your service account a name and a service account ID. This is like an email address and will be used to identify your service account in the future. Click `Continue` and `Done` to finish creating the service account.

### 2. Create a Key File

In the Google Cloud Console, go to [`IAM and Admin`](https://console.cloud.google.com/apis/credentials?project=pibasedemo) > `Service Accounts` page. Click the email address of the service account that you want to create a key for. Click the `Keys` tab. Click the `Add key` drop-down menu, then select `Create new key`.

Select `JSON` as the Key type and then click `Create`. This will download a JSON file that will contain your private key. Do not commit this file to the Github repository - name it `sa_<Location>_client_secrets.json` where \<Location\> is the name of new Location the service account is for - `.gitignore` file already has an entry to ignore all `*_secrets.json` files, and save the file to a root folder of this repository.

TBD: Save a copy of the file to secure storage (there is no possibility to re-download the Key File from Google Cloud Console).

Use the created `Key File` in the appliance project.

### 4. Grant Permissions to the Service Account

In the Google Cloud Console, go to [`IAM and Admin`](https://console.cloud.google.com/apis/credentials?project=pibasedemo) > `IAM` page > `Grant Access`. Enter the email address of the service account that you created, and select Role: `Basic` > `Editor`, then click `Save`.

### 5. Share a Drive Folder

We are setting up for uploading files from a local folder to a specific folder in Google Drive.

Go to your Google Drive and create a new folder. Right-click the folder, choose `Share` and add the email address of the service account you created in `step 1` as an `Editor` or a `Contributor` (Add and Edit files) to this folder.

Thus an appliance project with the `Key File` from `step 2` will be able to access this folder and upload files to it. The appliance project will not have access to any other resources on your Google Drive.

Copy the folder ID (the last portion of the URL in the Browser Address Bar) and paste it into the appliance project configuration file, along with the name of the `Key File`. Add the `Key File` to the appliance project builder specification (such as the appliance project's `conf.yaml` file).
