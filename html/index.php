<?
$url = "itdb.cgi";

$refresh = "0;url=" . urlencode($url);
header("refresh", $refresh);
?>
<meta http-equiv="refresh" content="<?= $refresh ?>">
