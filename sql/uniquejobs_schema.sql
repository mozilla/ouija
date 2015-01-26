USE ouija;

CREATE TABLE IF NOT EXISTS `uniquejobs` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `platform` varchar(64) NOT NULL,
  `buildtype` varchar(64) NOT NULL,
  `testtype` varchar(64) NOT NULL,
  primary key(id)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;
