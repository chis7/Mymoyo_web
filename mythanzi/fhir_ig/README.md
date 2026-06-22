# MyThanzi FHIR IG Upload Bundle

Edit `mythanzi-ig-bundle.json` as the project's FHIR implementation guide grows.

The file is a FHIR R5 `Bundle` with `type: transaction`. Each entry has a `PUT` request, so uploading it will create or replace the corresponding conformance resource on the configured HAPI FHIR server.

Upload from the Django project directory:

```powershell
python manage.py upload_fhir_ig
```

Upload a different file:

```powershell
python manage.py upload_fhir_ig --file fhir_ig/mythanzi-ig-bundle.json
```

The upload command uses `HAPI_FHIR_BASE_URL` from Django settings, for example `http://127.0.0.1:7201/fhir` outside Docker or `http://hapi-fhir:8080/fhir` inside Docker.

After upload, check resources in HAPI with URLs like:

- `/fhir/ImplementationGuide/mythanzi`
- `/fhir/StructureDefinition/mythanzi-client-patient`
- `/fhir/NamingSystem/client-reference`
- `/fhir/CodeSystem/mythanzi-user-role`

