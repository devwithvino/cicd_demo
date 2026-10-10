{{/* Common labels for every resource. */}}
{{- define "shipyard.labels" -}}
app.kubernetes.io/part-of: shipyard
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{/* Selector labels for one component. Call with (dict "root" $ "name" "api"). */}}
{{- define "shipyard.selector" -}}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/name: {{ .name }}
{{- end -}}

{{/* Fully qualified resource name for one component. */}}
{{- define "shipyard.fullname" -}}
{{ .root.Release.Name }}-{{ .name }}
{{- end -}}

{{/* Image reference: by digest when given, otherwise by tag. */}}
{{- define "shipyard.image" -}}
{{- $digest := (index .root.Values.images .name).digest -}}
{{- if $digest -}}
{{ .root.Values.image.registry }}-{{ .name }}@{{ $digest }}
{{- else -}}
{{ .root.Values.image.registry }}-{{ .name }}:{{ .root.Values.image.tag }}
{{- end -}}
{{- end -}}

{{/* Key Value connection URL. */}}
{{- define "shipyard.kvUrl" -}}
{{- if .Values.keyValue.enabled -}}
redis://{{ .Release.Name }}-kv:6379/0
{{- else -}}
{{ required "keyValue.externalUrl is required when keyValue.enabled is false" .Values.keyValue.externalUrl }}
{{- end -}}
{{- end -}}

{{/* Hardened container security context shared by every container. */}}
{{- define "shipyard.containerSecurity" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
runAsNonRoot: true
capabilities:
  drop: ["ALL"]
seccompProfile:
  type: RuntimeDefault
{{- end -}}
