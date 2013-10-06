$(function() {
  var today = new Date();
  var lastWeek = new Date(
    today.getFullYear(),
    today.getMonth(),
    today.getDate() - 7
    );

  $( '#from' ).datepicker({
    defaultDate: '-1w',
    numberOfMonths: 2,
    dateFormat: 'yy-mm-dd',
    maxDate: new Date(),
    onClose: function( selectedDate ) {
      $( '#to' ).datepicker( 'option', 'minDate', selectedDate );
    }
  })
  .datepicker('setDate', lastWeek);

  $( '#to' ).datepicker({
    numberOfMonths: 2,
    dateFormat: 'yy-mm-dd',
    maxDate: new Date(),
    onClose: function( selectedDate ) {
      $( '#from' ).datepicker( 'option', 'maxDate', selectedDate );
    }
  })
  .datepicker('setDate', today);
});
