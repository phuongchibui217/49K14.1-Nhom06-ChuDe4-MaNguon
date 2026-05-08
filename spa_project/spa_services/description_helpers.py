"""
Helper functions for Service description generation.

generate_service_description(service) — tự sinh mô tả chi tiết từ
name, category và variants khi description đang trống/quá ngắn/giống short_description.
"""

# Ngưỡng: description ngắn hơn thế này thì coi là "chưa có mô tả tốt"
MIN_DESCRIPTION_LENGTH = 80

# Mapping danh mục → lợi ích / đối tượng phù hợp
_CATEGORY_BENEFITS = {
    'massage': (
        'giảm căng thẳng, thư giãn cơ bắp và cải thiện tuần hoàn máu',
        'những ai thường xuyên làm việc văn phòng, người bị đau mỏi vai gáy, '
        'hoặc đơn giản là muốn tìm lại cảm giác thư thái sau một ngày dài',
    ),
    'cham soc da': (
        'làm sạch sâu, cấp ẩm và tái tạo làn da, giúp da sáng mịn và căng bóng',
        'những ai có làn da khô, sạm, lão hóa sớm hoặc muốn duy trì làn da khỏe mạnh',
    ),
    'goi dau': (
        'làm sạch da đầu, nuôi dưỡng tóc từ gốc đến ngọn và mang lại cảm giác thư giãn tức thì',
        'những ai muốn chăm sóc tóc chuyên sâu, giảm gàu, rụng tóc hoặc đơn giản là thư giãn đầu óc',
    ),
    'tay te bao chet': (
        'loại bỏ tế bào chết, thông thoáng lỗ chân lông và kích thích tái tạo da mới mịn màng',
        'những ai có da thô ráp, sạm màu hoặc muốn chuẩn bị da trước các liệu trình dưỡng da khác',
    ),
    'duong trang': (
        'làm đều màu da, giảm thâm nám và mang lại làn da trắng sáng rạng rỡ',
        'những ai muốn cải thiện tông màu da, giảm vết thâm sau mụn hoặc tàn nhang',
    ),
}


def _get_category_context(category_name: str):
    """Trả về (benefits, target) phù hợp với danh mục, hoặc giá trị mặc định."""
    if not category_name:
        return (
            'thư giãn toàn diện, phục hồi năng lượng và chăm sóc sắc đẹp từ bên trong',
            'tất cả khách hàng muốn tìm lại sự cân bằng và vẻ đẹp tự nhiên',
        )
    name_lower = category_name.lower()
    for key, value in _CATEGORY_BENEFITS.items():
        if key in name_lower:
            return value
    return (
        'thư giãn toàn diện, phục hồi năng lượng và chăm sóc sắc đẹp từ bên trong',
        'tất cả khách hàng muốn tìm lại sự cân bằng và vẻ đẹp tự nhiên',
    )


def _is_description_poor(service) -> bool:
    """
    Trả về True nếu description hiện tại cần được tự sinh lại:
    - Rỗng / None
    - Quá ngắn (< MIN_DESCRIPTION_LENGTH ký tự)
    - Giống hệt short_description (chỉ là bản copy)
    """
    desc = (service.description or '').strip()
    short = (service.short_description or '').strip()

    if not desc:
        return True
    if len(desc) < MIN_DESCRIPTION_LENGTH:
        return True
    if short and desc == short:
        return True
    return False


def generate_service_description(service) -> str:
    """
    Tự sinh mô tả chi tiết cho dịch vụ.

    Cấu trúc 5 phần:
    1. Giới thiệu dịch vụ (tên + danh mục)
    2. Công dụng / lợi ích nổi bật
    3. Đối tượng phù hợp
    4. Thông tin gói thời lượng / mức giá (nếu có)
    5. Gợi ý đặt lịch trước

    Chỉ nên gọi khi should_generate_description() == True.
    Trả về chuỗi — không lưu vào DB, caller tự quyết định.
    """
    name = service.name.strip()
    category_name = ''
    try:
        category_name = service.category.name.strip()
    except Exception:
        pass

    benefits, target = _get_category_context(category_name)

    # --- Thu thập thông tin variants ---
    variants_info = []
    try:
        for v in service.variants.order_by('sort_order', 'duration_minutes'):
            label = v.label or f'{v.duration_minutes} phút'
            price_fmt = f'{int(v.price):,}'.replace(',', '.') + 'đ'
            variants_info.append((label, v.duration_minutes, price_fmt))
    except Exception:
        pass

    # --- Xây dựng từng đoạn ---
    paragraphs = []

    # 1. Giới thiệu
    if category_name:
        paragraphs.append(
            f'{name} là liệu trình thuộc nhóm {category_name} tại Spa ANA — '
            f'được thiết kế để mang lại trải nghiệm chăm sóc chuyên sâu, '
            f'kết hợp kỹ thuật hiện đại và nguyên liệu thiên nhiên thuần khiết.'
        )
    else:
        paragraphs.append(
            f'{name} là dịch vụ chăm sóc cao cấp tại Spa ANA, '
            f'kết hợp kỹ thuật hiện đại và nguyên liệu thiên nhiên thuần khiết '
            f'để mang lại trải nghiệm thư giãn và phục hồi toàn diện.'
        )

    # 2. Công dụng / lợi ích
    paragraphs.append(
        f'Liệu trình giúp {benefits}. '
        f'Với đội ngũ kỹ thuật viên được đào tạo bài bản và sản phẩm đạt chuẩn, '
        f'Spa ANA cam kết mang lại kết quả rõ rệt ngay từ lần trải nghiệm đầu tiên.'
    )

    # 3. Đối tượng phù hợp
    paragraphs.append(
        f'Dịch vụ đặc biệt phù hợp với {target}. '
        f'Dù bạn đến để thư giãn sau giờ làm việc hay muốn chăm sóc bản thân định kỳ, '
        f'{name} đều sẵn sàng đáp ứng nhu cầu của bạn.'
    )

    # 4. Thông tin gói (nếu có)
    if variants_info:
        if len(variants_info) == 1:
            label, duration, price = variants_info[0]
            paragraphs.append(
                f'Dịch vụ có gói {label} với thời lượng {duration} phút, '
                f'mức giá {price} — bao gồm toàn bộ quy trình và sản phẩm chăm sóc.'
            )
        else:
            goi_lines = '\n'.join(
                f'  • {label} ({duration} phút) — {price}'
                for label, duration, price in variants_info
            )
            paragraphs.append(
                f'Khách hàng có thể lựa chọn gói thời lượng phù hợp với nhu cầu:\n{goi_lines}\n'
                f'Tất cả các gói đều bao gồm đầy đủ quy trình và sản phẩm chăm sóc chuyên dụng.'
            )

    # 5. Gợi ý đặt lịch
    paragraphs.append(
        f'Để được phục vụ tốt nhất, quý khách nên đặt lịch trước ít nhất 1–2 tiếng. '
        f'Đội ngũ Spa ANA luôn sẵn sàng tư vấn và hỗ trợ bạn chọn gói dịch vụ phù hợp nhất.'
    )

    return '\n\n'.join(paragraphs)


def should_generate_description(service) -> bool:
    """Public wrapper — kiểm tra xem có nên tự sinh description không."""
    return _is_description_poor(service)
