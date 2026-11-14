{{/* What each part is given, as in deploy/compose.yaml: each reads only its own keys. */}}

{{- define "a5s.env.gateway" -}}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_DATABASE_URL" "key" "database-gateway-url") }}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_SERVICE_TOKEN" "key" "service-token") }}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_SEAL_KEYS" "key" "seal-keys") }}
{{- range $name, $key := .Values.models.keys }}
{{ include "a5s.secretEnv" (dict "root" $ "name" $name "key" $key "optional" true) }}
{{- end }}
- name: A5S_TEAM
  value: {{ .Values.team | quote }}
{{ include "a5s.peopleEnv" . }}
{{ include "a5s.scenarioEnv" . }}
{{- with .Values.telemetry.endpoint }}
- name: OTEL_EXPORTER_OTLP_ENDPOINT
  value: {{ . | quote }}
{{- end }}
- name: A5S_PROVIDER_TIMEOUT
  value: {{ .Values.timeouts.provider | quote }}
{{ include "a5s.dbConnectEnv" . }}
{{- if .Values.officerAgrees.rubberStampFlag }}
- name: A5S_FLAG_RUBBER_STAMPS
  value: "true"
{{- end }}
{{- end }}

{{- define "a5s.env.channels" -}}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_DATABASE_URL" "key" "database-channels-url") }}
{{ include "a5s.peopleEnv" . }}
{{ include "a5s.scenarioEnv" . }}
{{ include "a5s.dbConnectEnv" . }}
{{- if and .Values.publishing.repo .Values.publishing.githubClientId }}
{{- $p := .Values.publishing }}
{{- range $name, $value := dict "A5S_GITHUB_CLIENT_ID" $p.githubClientId "A5S_GITHUB_REPO" $p.repo "A5S_GITHUB_BASE" $p.base "A5S_GITHUB_AGENTS_PATH" $p.agentsPath "A5S_GITHUB_URL" $p.githubUrl "A5S_GITHUB_API_URL" $p.githubApiUrl }}
- name: {{ $name }}  # publishing drafts as pull requests, as whoever publishes
  value: {{ $value | quote }}
{{- end }}
{{- end }}
{{- with .Values.sandbox.url }}
- name: A5S_SANDBOX_URL  # where the studio tries people's drafts, by the token it shares
  value: {{ . | quote }}
{{ include "a5s.secretEnv" (dict "root" $ "name" "A5S_SANDBOX_TOKEN" "key" "sandbox-token") }}
{{- end }}
{{- if .Values.officerAgrees.studioNames }}
- name: A5S_STUDIO_NAMES
  value: "true"
{{- end }}
{{- if .Values.officerAgrees.auditNames }}
- name: A5S_AUDIT_NAMES
  value: "true"
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
- name: A5S_ANCHOR_STORE
  value: {{ required "set anchor.store, where the ledger's locked copies go" .Values.anchor.store | quote }}
- name: A5S_ANCHOR_RETAIN_DAYS
  value: {{ .Values.anchor.retainDays | quote }}
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
- name: A5S_WORKER_TIMEOUT
  value: {{ .Values.timeouts.run | quote }}
{{- end }}

{{/* How long a part waits for a new database connection. */}}
{{- define "a5s.dbConnectEnv" -}}
- name: A5S_DB_CONNECT_TIMEOUT
  value: {{ .Values.timeouts.dbConnect | quote }}
{{- end }}

{{/* The jobs, as the database's administrator. */}}
{{- define "a5s.env.admin" -}}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_DATABASE_URL" "key" "database-admin-url") }}
- name: A5S_TEAM
  value: {{ .Values.team | quote }}
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
