{{/* A pod that runs as the database's administrator, once: call with (dict "root" $ "args"
(list ...) "passwords" bool "approval" bool). */}}
{{- define "a5s.adminPod" -}}
{{- $root := .root -}}
metadata:
  labels:
    {{- include "a5s.podLabels" (dict "root" $root "part" "admin") | nindent 4 }}
spec:
  restartPolicy: Never
  serviceAccountName: {{ printf "%s-admin" $root.Release.Name }}
  automountServiceAccountToken: false
  {{- with $root.Values.imagePullSecrets }}
  imagePullSecrets:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  securityContext:
    runAsNonRoot: true
    fsGroup: 10001
  containers:
    - name: admin
      image: {{ include "a5s.image" $root }}
      imagePullPolicy: {{ $root.Values.image.pullPolicy }}
      args: {{ toJson .args }}
      securityContext:
        {{- include "a5s.securityContext" $root | nindent 8 }}
      env:
        {{- include "a5s.scratch" $root | nindent 8 }}
        {{- include "a5s.env.admin" $root | nindent 8 }}
        {{- if .passwords }}
        {{- range $part := list "gateway" "channels" "scheduler" "anchor" }}
        {{- include "a5s.secretEnv" (dict "root" $root "name" (printf "A5S_DB_%s_PASSWORD" (upper $part)) "key" (printf "database-%s-password" $part)) | nindent 8 }}
        {{- end }}
        {{- end }}
      resources:
        {{- toYaml $root.Values.resources.jobs | nindent 8 }}
      volumeMounts:
        - name: scratch
          mountPath: /tmp
        {{- if .approval }}
        - name: approval
          mountPath: /approval
          readOnly: true
        {{- end }}
  volumes:
    - name: scratch
      emptyDir: {}
    {{- if .approval }}
    - name: approval
      configMap:
        name: {{ $root.Values.release.approval }}
    {{- end }}
{{- end }}
