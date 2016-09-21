USE ouija;

drop table jobpriorities;

CREATE TABLE IF NOT EXISTS `jobpriorities` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `platform` varchar(32) NOT NULL,
  `buildtype` varchar(32) NOT NULL,
  `testtype` varchar(64) NOT NULL,
  `priority` int(11) NOT NULL,
  `timeout` int(11) NOT NULL,
  `expires` date,
  `buildsystem` varchar(32) not NULL,
  primary key(id)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;
