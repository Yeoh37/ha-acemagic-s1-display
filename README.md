# ACEMAGIC S1 Display for Home Assistant

Application/add-on Home Assistant pour afficher l'état de Home Assistant sur le petit écran LCD du mini PC ACEMAGIC S1 / ACEMAGICIAN S1.

Affichage prévu :

- HOME ASSISTANT
- OK / EN FONCTIONNEMENT
- CPU utilisé
- RAM utilisée
- Heure

## Installation

1. Créer un dépôt GitHub public nommé `ha-acemagic-s1-display`.
2. Envoyer tout le contenu de ce dossier à la racine du dépôt.
3. Dans Home Assistant : `Paramètres > Applications > Installer une application`.
4. Ajouter le dépôt : `https://github.com/Yeoh37/ha-acemagic-s1-display`.
5. Installer `ACEMAGIC S1 Status`.
6. Démarrer l'application et consulter les journaux.

## Matériel ciblé

Écran USB HID détecté comme :

- VID:PID `04d9:fd01`
- souvent exposé par Linux via `/dev/hidraw0` et `/dev/hidraw1`

## Note importante

Le protocole de l'écran ACEMAGIC S1 peut varier selon les versions matérielles/firmware. Cette application contient plusieurs méthodes d'envoi HID. Si l'écran reste noir, les journaux indiquent la méthode tentée et les erreurs éventuelles.
