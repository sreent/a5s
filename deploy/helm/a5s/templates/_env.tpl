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
{{ include "a5s.dbConnectEnv" . }}
{{- if .Values.officerAgrees.studioNames }}
- name: A5S_STUDIO_NAMES
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
{{ include "a5s.dbConnectEnv" . }}
{{- end }}

{{- define "a5s.env.anchor" -}}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_DATABASE_URL" "key" "database-anchor-url") }}
- name: A5S_ANCHOR_STORE
  value: {{ required "set anchor.store, where the ledger's locked copies go" .Values.anchor.store | quote }}
- name: A5S_ANCHOR_RETAIN_DAYS
  value: {{ .Values.anchor.retainDays | quote }}
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
{{- end }}
