{{/* What each part is given, as in deploy/compose.yaml: each reads only its own keys. */}}

{{- define "a5s.env.gateway" -}}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_DATABASE_URL" "key" "database-gateway-url") }}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_SERVICE_TOKEN" "key" "service-token") }}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_OPERATOR_TOKEN" "key" "operator-token" "optional" true) }}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_SEAL_KEYS" "key" "seal-keys") }}
{{- range $name, $key := .Values.models.keys }}
{{ include "a5s.secretEnv" (dict "root" $ "name" $name "key" $key "optional" true) }}
{{- end }}
{{ include "a5s.teamEnv" . }}
{{ include "a5s.environmentEnv" . }}
{{ include "a5s.peopleEnv" . }}
{{ include "a5s.scenarioEnv" . }}
{{- range .Values.delegation.systems }}
{{ include "a5s.secretEnv" (dict "root" $ "name" (printf "A5S_DELEGATION_%s_SECRET" (upper (replace "-" "_" .name))) "key" (printf "delegation-secret-%s" .name)) }}
{{- end }}
{{- range .Values.tokens.mcp }}
{{ include "a5s.secretEnv" (dict "root" $ "name" (printf "A5S_MCP_%s_TOKEN" (upper .)) "key" (printf "mcp-token-%s" .)) }}
{{- end }}
{{- range .Values.tokens.repositories }}
{{ include "a5s.secretEnv" (dict "root" $ "name" (printf "A5S_REPOSITORY_%s_TOKEN" (upper .)) "key" (printf "repository-token-%s" .)) }}
{{- end }}
{{- with .Values.telemetry.endpoint }}
- name: OTEL_EXPORTER_OTLP_ENDPOINT
  value: {{ . | quote }}
{{- end }}
{{- with .Values.expires }}
- name: A5S_EXPIRES  # when the credentials a5s holds expire, for its status to say so
  value: {{ include "a5s.expires" . | quote }}
{{- end }}
- name: A5S_PROVIDER_TIMEOUT
  value: {{ .Values.timeouts.provider | quote }}
{{ include "a5s.dbConnectEnv" . }}
{{- with .Values.registry.tenant }}
- name: A5S_REGISTRY_TENANT  # IT's inventory: the core alone lists instances there
  value: {{ . | quote }}
- name: A5S_REGISTRY_CLIENT_ID
  value: {{ required "registry.clientId names the app the core signs in to the tenant as" $.Values.registry.clientId | quote }}
{{ include "a5s.secretEnv" (dict "root" $ "name" "A5S_REGISTRY_SECRET" "key" "registry-secret") }}
- name: A5S_REGISTRY_IDENTITIES
  value: {{ $.Values.registry.identities | quote }}
{{- end }}
{{- with .Values.mail.tenant }}
- name: A5S_MAIL_TENANT  # the shared mailboxes: the core alone reads them
  value: {{ . | quote }}
- name: A5S_MAIL_CLIENT_ID
  value: {{ required "mail.clientId names the app the core reads the mailboxes as" $.Values.mail.clientId | quote }}
{{ include "a5s.secretEnv" (dict "root" $ "name" "A5S_MAIL_CLIENT_SECRET" "key" "mail-secret") }}
{{- end }}
{{- end }}

{{- define "a5s.env.channels" -}}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_DATABASE_URL" "key" "database-channels-url") }}
{{ include "a5s.teamEnv" . }}
{{ include "a5s.environmentEnv" . }}
{{ include "a5s.peopleEnv" . }}
{{ include "a5s.scenarioEnv" . }}
{{ include "a5s.dbConnectEnv" . }}
{{- if and .Values.publishing.repo .Values.publishing.githubClientId }}
{{- $p := .Values.publishing }}
{{- range $name, $value := dict "A5S_GITHUB_CLIENT_ID" $p.githubClientId "A5S_GITHUB_REPO" $p.repo "A5S_GITHUB_BASE" $p.base "A5S_GITHUB_URL" $p.githubUrl "A5S_GITHUB_API_URL" $p.githubApiUrl }}
{{- if $value }}
- name: {{ $name }}  # publishing drafts as pull requests, as whoever publishes
  value: {{ $value | quote }}
{{- end }}
{{- end }}
{{- end }}
{{- with .Values.sandbox.url }}
- name: A5S_SANDBOX_URL  # where the studio tries people's drafts, by the token it shares
  value: {{ . | quote }}
{{ include "a5s.secretEnv" (dict "root" $ "name" "A5S_SANDBOX_TOKEN" "key" "sandbox-token") }}
{{- end }}
{{- end }}

{{- define "a5s.env.scheduler" -}}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_DATABASE_URL" "key" "database-scheduler-url") }}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_SERVICE_TOKEN" "key" "service-token") }}
- name: A5S_GATEWAY_URL
  value: {{ printf "http://%s-gateway:8700" .Release.Name | quote }}
- name: A5S_WORKER_URL  # the shared pool, for every agent without a pool of its own
  value: {{ printf "http://%s-worker:8702" .Release.Name | quote }}
{{- if include "a5s.pooled" . | fromJsonArray }}
- name: A5S_WORKER_URLS  # each agent's own pool
  value: {{ include "a5s.workerUrls" . | quote }}
- name: A5S_WORKER_SLOTS
  value: {{ include "a5s.workerSlots" . | quote }}
{{- end }}
- name: A5S_WORKER_WAIT
  value: {{ .Values.timeouts.workerWait | quote }}
{{ include "a5s.scenarioEnv" . }}
{{ include "a5s.dbConnectEnv" . }}
{{- end }}

{{- define "a5s.env.anchor" -}}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_DATABASE_URL" "key" "database-anchor-url") }}
{{ include "a5s.env.copies" . }}
{{- end }}

{{/* `a5s restore`'s, after the database is restored from a backup: the core's database, as its
role, and the ledger's copies, as the copier reaches them (docs/runbooks.md#restoring-from-a-backup) */}}
{{- define "a5s.env.restore" -}}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_DATABASE_URL" "key" "database-gateway-url") }}
{{ include "a5s.env.copies" . }}
{{- end }}

{{/* Where the ledger's copies are, and how to reach them and the database */}}
{{- define "a5s.env.copies" -}}
- name: A5S_ANCHOR_STORE
  value: {{ required "set anchor.store, where the ledger's locked copies go" .Values.anchor.store | quote }}
{{- with .Values.anchor.retainDays }}
- name: A5S_ANCHOR_RETAIN_DAYS
  value: {{ . | quote }}
{{- end }}
{{- with .Values.anchor.s3Endpoint }}
- name: AWS_ENDPOINT_URL_S3
  value: {{ . | quote }}
{{ include "a5s.secretEnv" (dict "root" $ "name" "AWS_ACCESS_KEY_ID" "key" "anchor-s3-access-key-id" "optional" true) }}
{{ include "a5s.secretEnv" (dict "root" $ "name" "AWS_SECRET_ACCESS_KEY" "key" "anchor-s3-secret-access-key" "optional" true) }}
{{- end }}
{{- with .Values.anchor.s3Region }}
- name: AWS_REGION
  value: {{ . | quote }}
{{- end }}
{{ include "a5s.dbConnectEnv" . }}
{{- end }}

{{- define "a5s.env.worker" -}}
- name: A5S_GATEWAY_URL
  value: {{ printf "http://%s-gateway:8700" .Release.Name | quote }}
{{- with .Values.timeouts.run }}
- name: A5S_WORKER_TIMEOUT
  value: {{ . | quote }}
{{- end }}
{{- end }}

{{/* How long a part waits for a new database connection. */}}
{{- define "a5s.dbConnectEnv" -}}
{{- with .Values.timeouts.dbConnect }}
- name: A5S_DB_CONNECT_TIMEOUT
  value: {{ . | quote }}
{{- end }}
{{- end }}

{{/* The directory's team that runs a5s, if the deployment names one. */}}
{{/* Which deployment this is, for the band across the top of every page the channels serve,
and for the doctor, which runs with the core's settings. */}}
{{- define "a5s.environmentEnv" -}}
{{- with .Values.environment.kind }}
- name: A5S_ENVIRONMENT
  value: {{ . | quote }}
{{- end }}
{{- with .Values.environment.name }}
- name: A5S_ENVIRONMENT_NAME
  value: {{ . | quote }}
{{- end }}
{{- end }}

{{- define "a5s.teamEnv" -}}
{{- with .Values.team }}
- name: A5S_TEAM
  value: {{ . | quote }}
{{- end }}
{{- end }}

{{/* The jobs, as the database's administrator. */}}
{{- define "a5s.env.admin" -}}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_DATABASE_URL" "key" "database-admin-url") }}
{{ include "a5s.teamEnv" . }}
{{ include "a5s.scenarioEnv" . }}
{{- end }}

{{/* The scenario a5s serves, if not the image's sample: for the parts compose gives it to. */}}
{{- define "a5s.scenarioEnv" -}}
{{- range $name, $value := dict "A5S_SCENARIO" .Values.scenario.class "A5S_SCENARIO_DIR" .Values.scenario.folder "A5S_AGENTS_DIR" .Values.scenario.agents }}
{{- if $value }}
- name: {{ $name }}
  value: {{ $value | quote }}
{{- end }}
{{- end }}
{{- end }}

{{/* The credentials values' expires names, as A5S_EXPIRES takes them: name=day, by commas. */}}
{{- define "a5s.expires" -}}
{{- $pairs := list }}
{{- range $name, $day := . }}
{{- $pairs = append $pairs (printf "%s=%v" $name $day) }}
{{- end }}
{{- join "," $pairs }}
{{- end }}
