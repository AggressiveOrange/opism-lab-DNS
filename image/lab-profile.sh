# Shell helpers for the DNS lab (students' ttyd sessions).
if [ -n "$STUDENT_ID" ]; then
  export ZONE="$STUDENT_ID.lab"
  export ZONEFILE="/lab/zone/$STUDENT_ID.lab.zone"
  alias zone-edit='nano "$ZONEFILE"'
  alias zone-check='named-checkzone "$ZONE" "$ZONEFILE"'
  alias zone-reload='named-checkzone "$ZONE" "$ZONEFILE" && rndc reload "$ZONE"'
  alias named-stop='rndc stop'
  alias named-start='named -u bind -c /lab/named.conf'
  alias querylog='tail -f /var/log/named/queries.log'
  cat <<EOF

  Стенд DNS. Ваша зона: $ZONE   Авторитативний сервер: $STUDENT_IP
  Резолвери: 10.53.0.53 (resolver-a), 10.53.0.54 (resolver-b, serve-expired)
  Root: 10.53.0.2   TLD lab.: 10.53.0.3   Веб: 10.53.0.80 (web-a), 10.53.0.81 (web-b)

  zone-edit     редагувати файл зони        zone-check   перевірити синтаксис
  zone-reload   перевірити і перезавантажити зону
  named-stop / named-start                  зупинити / запустити свій сервер
  querylog      журнал запитів до вашого сервера (Ctrl+C для виходу)

EOF
fi
