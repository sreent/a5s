{{/* The image every part runs: a release's, by its digest, or a tag only to try it out. */}}
{{- define "a5s.image" -}}
{{- if .Values.image.digest -}}
{{ .Values.image.repository }}@{{ .Values.image.digest }}
{{- else if .Values.image.tag -}}
{{ .Values.image.repository }}:{{ .Values.image.tag }}
{{- else -}}
{{ fail "set image.digest to a release's image, by its digest, so what runs is what was approved" }}
{{- end -}}
{{- end }}

{{- define "a5s.labels" -}}
app.kubernetes.io/name: a5s
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end }}

{{/* What selects one part's pods: call with (dict "root" $ "part" "gateway"). */}}
{{- define "a5s.selector" -}}
app.kubernetes.io/name: a5s
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .part }}
{{- end }}

{{/* A part's pods: what selects them, and the rest of the labels, each once. */}}
{{- define "a5s.podLabels" -}}
{{ include "a5s.selector" . }}
app.kubernetes.io/version: {{ .root.Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .root.Chart.Name .root.Chart.Version }}
{{- end }}

{{/* Each container runs as a5s's own user, with nothing it doesn't need. */}}
{{- define "a5s.securityContext" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
runAsNonRoot: true
runAsUser: 10001
runAsGroup: 10001
capabilities:
  drop: ["ALL"]
seccompProfile:
  type: RuntimeDefault
{{- end }}

{{/* A variable from a key of the Secret. */}}
{{- define "a5s.secretEnv" -}}
- name: {{ .name }}
  valueFrom:
    secretKeyRef:
      name: {{ .root.Values.secret }}
      key: {{ .key }}
      {{- if .optional }}
      optional: true
      {{- end }}
{{- end }}

{{/* How people reach a5s and sign in: for the gateway and the channels. */}}
{{- define "a5s.peopleEnv" -}}
{{- $p := .Values.people -}}
{{- range $name, $value := dict "A5S_OIDC_ISSUER" $p.oidcIssuer "A5S_OIDC_AUDIENCE" $p.oidcAudience "A5S_OIDC_PERSON_CLAIM" $p.oidcPersonClaim "A5S_OIDC_DIRECTORY_PREFIX" $p.oidcDirectoryPrefix "A5S_OIDC_METADATA_URL" $p.oidcMetadataUrl "A5S_WEBCHAT_CLIENT_ID" $p.webchatClientId "A5S_PUBLIC_URL" $p.publicUrl "A5S_MATRIX_HOMESERVER" $.Values.matrix.homeserver "A5S_MATRIX_SERVER_NAME" $.Values.matrix.serverName }}
{{- if $value }}
- name: {{ $name }}
  value: {{ $value | quote }}
{{- end }}
{{- end }}
{{- if .Values.matrix.homeserver }}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_MATRIX_AS_TOKEN" "key" "matrix-as-token") }}
{{ include "a5s.secretEnv" (dict "root" . "name" "A5S_MATRIX_HS_TOKEN" "key" "matrix-hs-token") }}
{{- end }}
{{- if .Values.teams.tenantId }}
- name: A5S_TEAMS_TENANT_ID
  value: {{ .Values.teams.tenantId | quote }}
- name: A5S_TEAMS_BOTS
  value: {{ include "a5s.teamsBots" . | quote }}
{{- range .Values.teams.bots }}
{{ include "a5s.secretEnv" (dict "root" $ "name" (printf "A5S_TEAMS_SECRET_%s" (upper .agent)) "key" (printf "teams-secret-%s" .agent)) }}
{{- end }}
{{- end }}
{{- end }}

{{/* Each agent's bot, as a5s reads them: its app id, and the variable its secret is in. */}}
{{- define "a5s.teamsBots" -}}
{{- $bots := list -}}
{{- range .Values.teams.bots -}}
{{- $bots = append $bots (dict "agent" .agent "app_id" .appId "secret_env" (printf "A5S_TEAMS_SECRET_%s" (upper .agent))) -}}
{{- end -}}
{{- toJson $bots -}}
{{- end }}

{{/* Where a5s writes what it must: nothing else of the image is writable. */}}
{{- define "a5s.scratch" -}}
- name: HOME
  value: /tmp
{{- end }}
