$(document).ready(function () {
    $('.toggle').click(function () {
        $('.toggle').toggleClass('active')
        $('nav').toggleClass('active')
    })
})

$("[data-fancybox]").fancybox();

$(".items").isotope({
    filter: '*',
    animationOption: {
        duration: 1500,
        easing: 'linear',
        queue: false
    }
})

$("#filters a").click(function () {
    var pre = $("#filters .current");
    pre.addClass("prev");
    pre.removeClass("current");
    var curr = $(this).children("button");
    console.log(curr)
    curr.addClass("current");
    curr.removeClass("prev");
    $(".items").isotope({
        filter: $(this).attr("data-filter"),
        animationOption: {
            duration: 1500,
            easing: 'linear',
            queue: false
        }
    })
})