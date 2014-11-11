DROP DATABASE IF EXISTS ouija;

CREATE DATABASE ouija;
USE ouija;

CREATE TABLE IF NOT EXISTS `testjobs` (
  `id` int(11) NOT NULL,
  `log` text NOT NULL,
  `slave` varchar(64) NOT NULL,
  `result` varchar(32) NOT NULL,
  `duration` int(11) NOT NULL,
  `platform` varchar(32) NOT NULL,
  `buildtype` varchar(32) NOT NULL,
  `testtype` varchar(64) NOT NULL,
  `bugid` text NOT NULL,
  `branch` varchar(64) NOT NULL,
  `revision` varchar(32) NOT NULL,
  `date` datetime NOT NULL,
-- regression: 0: no regression; 1: test failure, -1: build failure, etc.
  `regression` int(11) NOT NULL,
  primary key(id),
  index `revision` (`revision`),
  index `date` (`date`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;
